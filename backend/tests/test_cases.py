"""Phase 9: investigation cases — creation, assignment, transitions, evidence, justified decisions,
authorization, tenant isolation, timeline and audit."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import (
    Alert,
    AuditEvent,
    FinancialAidApplication,
    IdentityVerification,
    InvestigationCase,
    Notification,
    User,
)
from app.models.enums import CaseDecisionType, CaseResolution
from app.services import audit
from app.services import cases as service
from tests.conftest import LS_INVESTIGATOR, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded

ANALYST = "analyst@northbridge.demo"
JUSTIFY = "Reviewed the alert, risk signals and verification history before deciding."


def _app(db: Session, scenario: str) -> FinancialAidApplication:
    app = db.scalar(select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == scenario))
    assert app is not None
    return app


def _user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _open(client: TestClient, app: FinancialAidApplication, **extra: object) -> dict:
    res = client.post("/api/v1/cases", json={"application_id": str(app.id), **extra})
    assert res.status_code == 201, res.text
    return res.json()


def _decide(client: TestClient, case_id: str, decision: str, outcome: str | None = None, **overrides: object):  # type: ignore[no-untyped-def]
    body = {"decision": decision, "outcome": outcome, "justification": JUSTIFY, "acknowledged": True, **overrides}
    return client.post(f"/api/v1/cases/{case_id}/decision", json=body)


class TestCreation:
    def test_opening_a_case_links_alerts_and_attaches_the_evidence(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "unusual_disbursement")
        case = _open(as_user(NB_INVESTIGATOR), app)
        assert case["status"] == "new" and case["finding"] == "suspicious_activity"
        assert case["reference"].startswith("CASE-") and case["application"]["reference"] == app.reference
        assert case["priority"] in ("high", "urgent") and case["due_at"]
        assert case["title"].startswith("Unusual disbursement activity")
        types = {e["evidence_type"] for e in case["evidence"]}
        assert {"alert", "risk_assessment", "disbursement"} <= types
        assessment = next(e for e in case["evidence"] if e["evidence_type"] == "risk_assessment")
        assert assessment["data"]["signals"] and assessment["data"]["rules_version"].startswith("rules-")
        assert case["alerts"] and all(a["status"] == "in_investigation" for a in case["alerts"])

    def test_one_open_case_per_application(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "unusual_disbursement")
        client = as_user(NB_INVESTIGATOR)
        first = _open(client, app)
        again = client.post("/api/v1/cases", json={"application_id": str(app.id)})
        assert again.status_code == 409 and again.json()["error"]["details"]["case_id"] == first["id"]

    def test_officer_can_refer_but_not_assign_or_decide(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _app(db, "unusual_disbursement")
        officer = as_user(NB_OFFICER)
        marcus = _user(db, NB_INVESTIGATOR)
        assert (
            officer.post(
                "/api/v1/cases", json={"application_id": str(app.id), "assigned_to_id": str(marcus.id)}
            ).status_code
            == 409
        )
        case = _open(officer, app)
        assert (
            officer.post(f"/api/v1/cases/{case['id']}/assign", json={"assigned_to_id": str(marcus.id)}).status_code
            == 403
        )
        assert _decide(officer, case["id"], "escalate").status_code == 403
        assert officer.post(f"/api/v1/cases/{case['id']}/notes", json={"body": "Officer note"}).status_code == 403


class TestAssignment:
    def test_assign_reassign_and_notify(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        dana, marcus = _user(db, ANALYST), _user(db, NB_INVESTIGATOR)
        assignees = client.get("/api/v1/cases/assignees").json()
        assert {a["email"] for a in assignees} >= {ANALYST, NB_INVESTIGATOR}
        assert NB_AUDITOR not in {a["email"] for a in assignees}

        res = client.post(
            f"/api/v1/cases/{case['id']}/assign", json={"assigned_to_id": str(dana.id), "note": "Her queue"}
        )
        assert res.status_code == 200 and res.json()["assigned_to"]["email"] == ANALYST
        assert db.scalar(
            select(Notification).where(Notification.user_id == dana.id, Notification.kind == "case_assigned")
        )
        res = client.post(f"/api/v1/cases/{case['id']}/assign", json={"assigned_to_id": str(marcus.id)})
        assert res.json()["assigned_to"]["email"] == NB_INVESTIGATOR
        event = db.scalars(select(AuditEvent).where(AuditEvent.action == "case.assign")).all()[-1]
        assert event.details["previous"] == ANALYST and event.details["assigned_to"] == NB_INVESTIGATOR

    def test_assignee_must_be_an_in_scope_investigator(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        url = f"/api/v1/cases/{case['id']}/assign"
        assert client.post(url, json={"assigned_to_id": str(_user(db, LS_INVESTIGATOR).id)}).status_code == 404
        assert client.post(url, json={"assigned_to_id": str(_user(db, NB_AUDITOR).id)}).status_code == 409


class TestTransitions:
    def test_full_lifecycle_and_invalid_moves(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        url = f"/api/v1/cases/{case['id']}"
        started = client.patch(url, json={"status": "under_review"})
        assert started.status_code == 200 and started.json()["status"] == "under_review"
        assert started.json()["assigned_to"]["email"] == NB_INVESTIGATOR  # starting review claims an unassigned case
        assert client.patch(url, json={"status": "under_review"}).status_code == 409
        assert client.patch(url, json={"status": "resolved"}).status_code == 422  # only via a decision

        escalated = _decide(client, case["id"], "escalate").json()
        assert escalated["status"] == "escalated" and escalated["finding"] == "suspected_fraud"
        assert _decide(client, case["id"], "close").status_code == 409  # must be resolved first
        resolved = _decide(client, case["id"], "resolve", "insufficient_evidence").json()
        assert resolved["status"] == "resolved" and resolved["finding"] == "not_substantiated"
        assert all(a["status"] == "resolved" for a in resolved["alerts"])

        reopened = _decide(client, case["id"], "reopen").json()
        assert reopened["status"] == "under_review" and reopened["resolution"] is None
        assert all(a["status"] == "in_investigation" for a in reopened["alerts"])
        _decide(client, case["id"], "resolve", "no_fraud_found")
        closed = _decide(client, case["id"], "close").json()
        assert closed["status"] == "closed" and closed["closed_at"]
        assert [d["decision"] for d in closed["decisions"]] == ["escalate", "resolve", "reopen", "resolve", "close"]

        for blocked in (
            client.post(f"{url}/notes", json={"body": "Too late"}),
            client.post(
                f"{url}/evidence", json={"evidence_type": "document_note", "title": "x" * 5, "summary": "y" * 5}
            ),
            _decide(client, case["id"], "reopen"),
            client.patch(url, json={"title": "Renamed after closure"}),
        ):
            assert blocked.status_code == 409


class TestEvidence:
    def test_records_are_snapshotted_server_side_and_scoped(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        app = _app(db, "control_siblings")  # no alerts, so evidence starts with the assessment only
        case = _open(client, app)
        url = f"/api/v1/cases/{case['id']}/evidence"
        res = client.post(url, json={"evidence_type": "application", "ref_id": str(app.id), "title": "Forged title"})
        assert res.status_code == 200
        snap = next(e for e in res.json()["evidence"] if e["evidence_type"] == "application")
        assert snap["ref_label"] == app.reference and snap["added_by"]["email"] == NB_INVESTIGATOR
        assert client.post(url, json={"evidence_type": "application", "ref_id": str(app.id)}).status_code == 409

        foreign = db.scalar(
            select(IdentityVerification)
            .join(IdentityVerification.student)
            .where(IdentityVerification.organization_id != app.organization_id)
        )
        assert foreign is not None
        assert client.post(url, json={"evidence_type": "verification", "ref_id": str(foreign.id)}).status_code == 404
        assert client.post(url, json={"evidence_type": "document_note"}).status_code == 422
        note = client.post(
            url, json={"evidence_type": "document_note", "title": "Bank letter", "summary": "Letter on file"}
        )
        assert note.status_code == 200

    def test_failed_verifications_are_attached_when_opening(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        case = _open(as_user(NB_INVESTIGATOR), _app(db, "identity_impersonation"))
        verification = next(e for e in case["evidence"] if e["evidence_type"] == "verification")
        assert verification["data"]["pad_result"] == "attack_detected"


class TestDecisions:
    def test_decisions_require_justification_and_acknowledgement(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        assert _decide(client, case["id"], "escalate", justification="too short").status_code == 422
        assert _decide(client, case["id"], "escalate", acknowledged=False).status_code == 422
        assert _decide(client, case["id"], "resolve").status_code == 422  # outcome required
        assert _decide(client, case["id"], "escalate", "confirmed_fraud").status_code == 422  # outcome only for resolve
        short_confirm = _decide(
            client, case["id"], "resolve", "confirmed_fraud", justification="Twenty-plus characters but brief"
        )
        assert short_confirm.status_code == 422

    def test_confirmed_finding_records_who_and_when(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        app = _app(db, "unusual_disbursement")
        case = _open(client, app)
        why = (
            "Outsized refund to a destination changed two days earlier; the student confirmed they did not request it."
        )
        res = _decide(client, case["id"], "resolve", "confirmed_fraud", justification=why).json()
        assert res["finding"] == "confirmed_fraud" and res["resolution"] == "confirmed_fraud"
        decision = res["decisions"][-1]
        assert (
            decision["decided_by"]["email"] == NB_INVESTIGATOR
            and decision["decided_at"]
            and decision["justification"] == why
        )
        db.expire_all()
        refreshed = db.get(FinancialAidApplication, app.id)
        assert refreshed.review_status == "escalated" and refreshed.status == app.status  # type: ignore[union-attr]

    def test_cases_can_close_without_labelling_anyone_fraudulent(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        app = _app(db, "unusual_disbursement")
        case = _open(client, app)
        res = _decide(client, case["id"], "resolve", "no_fraud_found").json()
        assert res["finding"] == "not_substantiated" and res["status"] == "resolved"
        db.expire_all()
        assert db.get(FinancialAidApplication, app.id).review_status == "cleared"  # type: ignore[union-attr]

    def test_confirmed_fraud_requires_evidence(self, db: Session) -> None:
        marcus = _user(db, NB_INVESTIGATOR)
        case = InvestigationCase(
            organization_id=marcus.organization_id,
            reference="CASE-99999",
            title="Manual case without evidence",
            fraud_category="application",
            created_by_id=marcus.id,
        )
        db.add(case)
        db.flush()
        with pytest.raises(ConflictError, match="evidence"):
            service.decide(
                db,
                case,
                marcus,
                decision=CaseDecisionType.RESOLVE,
                outcome=CaseResolution.CONFIRMED_FRAUD,
                justification="x" * 80,
                request=None,
            )

    def test_legacy_resolve_endpoint_still_works(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        res = client.post(
            f"/api/v1/cases/{case['id']}/resolve", json={"resolution": "insufficient_evidence", "summary": JUSTIFY}
        )
        assert res.status_code == 200 and res.json()["decisions"][0]["outcome"] == "insufficient_evidence"


class TestAccessAndAudit:
    def test_auditor_reads_but_cannot_change(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        seeded = db.scalar(select(InvestigationCase).where(InvestigationCase.status == "escalated"))
        auditor = as_user(NB_AUDITOR)
        assert auditor.get("/api/v1/cases").json()["total"] >= 1
        assert auditor.get(f"/api/v1/cases/{seeded.id}").status_code == 200  # type: ignore[union-attr]
        assert auditor.post(f"/api/v1/cases/{seeded.id}/notes", json={"body": "Not allowed"}).status_code == 403  # type: ignore[union-attr]
        assert auditor.post("/api/v1/cases", json={"application_id": str(uuid.uuid4())}).status_code == 403

    def test_tenant_isolation(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        case = _open(as_user(NB_INVESTIGATOR), _app(db, "unusual_disbursement"))
        lakeshore = as_user(LS_INVESTIGATOR)
        assert lakeshore.get(f"/api/v1/cases/{case['id']}").status_code == 404
        assert lakeshore.post(f"/api/v1/cases/{case['id']}/notes", json={"body": "Cross-tenant"}).status_code == 404
        assert _decide(lakeshore, case["id"], "escalate").status_code == 404
        listing = lakeshore.get("/api/v1/cases", params={"page_size": 100}).json()["items"]
        assert case["id"] not in {c["id"] for c in listing}
        assert lakeshore.post("/api/v1/cases", json={"application_id": case["application_id"]}).status_code == 404

    def test_workflow_is_fully_audited_with_a_timeline(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        case = _open(client, _app(db, "unusual_disbursement"))
        url = f"/api/v1/cases/{case['id']}"
        client.post(f"{url}/assign", json={"assigned_to_id": str(_user(db, ANALYST).id)})
        client.patch(url, json={"status": "under_review"})
        client.post(f"{url}/notes", json={"body": "Called the student via the number on file."})
        detail = _decide(client, case["id"], "resolve", "no_fraud_found").json()

        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.target_ref == case["reference"])).all()
        for expected in (
            "case.create",
            "case.evidence_add",
            "case.assign",
            "case.status_change",
            "case.note_add",
            "case.decision.resolve",
        ):
            assert expected in actions
        decision_event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "case.decision.resolve", AuditEvent.target_ref == case["reference"]
            )
        )
        assert decision_event.details["justification"] == JUSTIFY and decision_event.actor_email == NB_INVESTIGATOR  # type: ignore[union-attr]
        kinds = [t["kind"] for t in detail["timeline"]]
        assert "alert.raised" in kinds and kinds[-1] == "case.decision.resolve"
        assert [t["at"] for t in detail["timeline"]] == sorted(t["at"] for t in detail["timeline"])
        assert audit.verify_chain(db).valid

    def test_list_filters_and_summary(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        mine = client.get(
            "/api/v1/cases", params={"assignee": "me", "status": ["escalated", "under_review", "new"]}
        ).json()
        assert mine["total"] >= 1 and all(c["assigned_to"]["email"] == NB_INVESTIGATOR for c in mine["items"])
        suspected = client.get("/api/v1/cases", params={"finding": "suspected_fraud"}).json()["items"]
        assert suspected and all(c["finding"] == "suspected_fraud" for c in suspected)
        summary = client.get("/api/v1/cases/summary").json()
        assert summary["open"] >= 1 and summary["by_finding"]
        assert client.get("/api/v1/cases", params={"status": "bogus"}).status_code == 422


def test_seeded_caseload_has_distinct_findings(db: Session) -> None:
    findings = {c.finding for c in db.scalars(select(InvestigationCase))}
    assert {"suspected_fraud", "not_substantiated", "suspicious_activity"} <= findings
    assert db.scalar(select(Alert).where(Alert.status == "in_investigation")) is not None
