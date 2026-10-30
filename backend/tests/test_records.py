"""Phase 5: synthetic data guarantees, application and disbursement APIs, audited PII reveal."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Disbursement, FinancialAidApplication, StudentIdentityToken
from app.models.enums import DisbursementStatus
from tests.conftest import LS_INVESTIGATOR, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded


def _app(db: Session, scenario: str, org_slug: str | None = None) -> FinancialAidApplication:
    stmt = select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == scenario)
    apps = [a for a in db.scalars(stmt) if org_slug is None or _slug(db, a.organization_id) == org_slug]
    return apps[0]


def _slug(db: Session, org_id) -> str:  # type: ignore[no-untyped-def]
    from app.models import Organization

    return db.get(Organization, org_id).slug  # type: ignore[union-attr]


class TestSyntheticDataPrivacy:
    def test_no_raw_identifiers_or_plaintext_names_are_persisted(self, engine: Engine, db: Session) -> None:
        raw = Path(engine.url.database).read_bytes()  # type: ignore[arg-type]
        assert not re.search(rb"000-\d{2}-\d{4}", raw), "SSN-shaped value found in database file"
        assert b"Robinson" not in raw and b"Maya" not in raw, "student names must be encrypted at rest"
        tokens = db.scalars(select(StudentIdentityToken.token_value)).all()
        assert tokens and all(re.fullmatch(r"[0-9a-f]{64}", t) for t in tokens)

    def test_every_record_is_marked_synthetic(self, db: Session) -> None:
        assert db.scalar(select(func.count()).where(FinancialAidApplication.is_synthetic.is_(False))) == 0
        assert db.scalar(select(func.count()).where(Disbursement.is_synthetic.is_(False))) == 0

    def test_scenarios_are_planted_as_documented(self, db: Session) -> None:
        def count(key: str) -> int:
            stmt = select(func.count()).where(FinancialAidApplication.scenario_key == key)
            return db.scalar(stmt) or 0

        assert count("duplicate_identity") == 4
        assert count("shared_destination") == 6
        assert count("coordinated_network") == 8
        assert count("identity_impersonation") == count("unusual_disbursement") == 1
        ring_devices = db.scalars(
            select(FinancialAidApplication.device_token).where(
                FinancialAidApplication.scenario_key == "coordinated_network"
            )
        ).all()
        assert len(set(ring_devices)) == 1


class TestApplicationsApi:
    def test_list_is_tenant_scoped(self, as_user) -> None:  # type: ignore[no-untyped-def]
        page = as_user(LS_INVESTIGATOR).get("/api/v1/applications", params={"page_size": 100}).json()
        assert page["total"] > 0
        assert {row["organization"]["slug"] for row in page["items"]} == {"lakeshore"}

    def test_filter_search_and_sort(self, as_user) -> None:  # type: ignore[no-untyped-def]
        c = as_user(NB_INVESTIGATOR)
        dup = c.get("/api/v1/applications", params={"scenario": "duplicate_identity"}).json()
        assert dup["total"] == 3  # the fourth duplicate lives at another institution
        ref = dup["items"][0]["reference"]
        found = c.get("/api/v1/applications", params={"q": ref.lower()}).json()
        assert [r["reference"] for r in found["items"]] == [ref]
        asc = c.get("/api/v1/applications", params={"sort": "reference", "direction": "asc"}).json()["items"]
        assert [r["reference"] for r in asc] == sorted(r["reference"] for r in asc)

    def test_rejects_invalid_filters(self, as_user) -> None:  # type: ignore[no-untyped-def]
        c = as_user(NB_INVESTIGATOR)
        assert c.get("/api/v1/applications", params={"risk_level": "extreme"}).status_code == 422
        assert c.get("/api/v1/applications", params={"page_size": 1000}).status_code == 422
        assert c.get("/api/v1/applications", params={"sort": "password"}).status_code == 422

    def test_detail_masks_identity_and_links_related_records(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "duplicate_identity", "northbridge")
        detail = as_user(NB_INVESTIGATOR).get(f"/api/v1/applications/{app.id}").json()
        assert re.fullmatch(r"\w\*\*\* \w\*\*\*", detail["student"]["masked_name"])
        ssn = next(g for g in detail["related"] if g["kind"] == "ssn")
        assert len(ssn["matches"]) == 2 and ssn["other_institution_matches"] == 1
        assert {m["organization_name"] for m in ssn["matches"]} == {"Northbridge State University"}
        assert any(g["kind"] == "device" for g in detail["related"])
        token = next(t for t in detail["student_detail"]["identity_tokens"] if t["token_type"] == "ssn")
        assert token["handle"].startswith("TKN-") and token["shared_other_institutions"] == 1

    def test_cross_tenant_detail_is_not_found(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "identity_impersonation")
        assert as_user(LS_INVESTIGATOR).get(f"/api/v1/applications/{app.id}").status_code == 404

    def test_review_decision_is_audited_and_permissioned(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "duplicate_identity", "northbridge")
        body = {"review_status": "escalated", "application_status": "on_hold", "note": "Shared SSN across apps"}
        assert as_user(NB_AUDITOR).patch(f"/api/v1/applications/{app.id}/review", json=body).status_code == 403
        res = as_user(NB_OFFICER).patch(f"/api/v1/applications/{app.id}/review", json=body)
        assert res.status_code == 200 and res.json()["status"] == "on_hold"
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "application.review"))
        assert event is not None and event.target_ref == app.reference and event.details["note"] == body["note"]


class TestPiiReveal:
    def test_reveal_requires_permission_and_reason_and_is_audited(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "identity_impersonation")
        url = f"/api/v1/students/{app.student_id}/reveal"
        assert as_user(NB_AUDITOR).post(url, json={"reason": "Routine audit check"}).status_code == 403
        investigator = as_user(NB_INVESTIGATOR)
        assert investigator.post(url, json={"reason": "x"}).status_code == 422
        res = investigator.post(url, json={"reason": "Contacting student about refund change"})
        assert res.status_code == 200 and res.json()["first_name"] == "Maya"
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "student.pii_reveal"))
        assert event is not None and event.category == "data_access"
        assert event.details["reason"] == "Contacting student about refund change"


class TestDisbursementsApi:
    def _scheduled_refund(self, db: Session) -> Disbursement:
        app = _app(db, "identity_impersonation")
        return db.scalar(
            select(Disbursement).where(
                Disbursement.application_id == app.id, Disbursement.status == DisbursementStatus.SCHEDULED
            )
        )  # type: ignore[return-value]

    def test_destination_usage_spans_institutions_without_exposing_them(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "shared_destination", "northbridge")
        refund = db.scalar(
            select(Disbursement).where(
                Disbursement.application_id == app.id, Disbursement.fund_type == "credit_balance_refund"
            )
        )
        detail = as_user(NB_INVESTIGATOR).get(f"/api/v1/disbursements/{refund.id}").json()  # type: ignore[union-attr]
        usage = detail["destination_usage"]
        assert usage == {**usage, "students_in_scope": 4, "students_other_institutions": 2}
        assert all(d["organization"]["slug"] == "northbridge" for d in detail["same_destination"])

    def test_hold_and_release_lifecycle(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        refund = self._scheduled_refund(db)
        officer = as_user(NB_OFFICER)
        url = f"/api/v1/disbursements/{refund.id}"
        held = officer.post(f"{url}/hold", json={"reason": "Destination changed overnight before refund"})
        assert held.status_code == 200 and held.json()["status"] == "held"
        assert officer.post(f"{url}/hold", json={"reason": "Second hold attempt"}).status_code == 409
        released = officer.post(f"{url}/release", json={"reason": "Student verified in person"})
        assert released.json()["status"] == "scheduled" and released.json()["hold_reason"] is None
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.target_ref == refund.reference)).all()
        assert actions == ["disbursement.hold", "disbursement.release"]

    def test_auditor_cannot_hold(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        refund = self._scheduled_refund(db)
        res = as_user(NB_AUDITOR).post(f"/api/v1/disbursements/{refund.id}/hold", json={"reason": "Not allowed here"})
        assert res.status_code == 403

    def test_summary_matches_list(self, as_user) -> None:  # type: ignore[no-untyped-def]
        c = as_user(NB_INVESTIGATOR)
        summary = c.get("/api/v1/disbursements/summary").json()
        listing = c.get("/api/v1/disbursements", params={"page_size": 1}).json()
        assert summary["total_count"] == listing["total"] > 0
