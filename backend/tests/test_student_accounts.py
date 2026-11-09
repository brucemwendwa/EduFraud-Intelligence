"""Student ID-linked financial aid: accounts, cards, transactions, security events, verification requests.

Covers the five demonstration scenarios end to end through the API, the legitimate controls,
signed provider webhooks, permissions, tenant isolation and the audit trail.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.v1.provider_events import sign
from app.db.types import utcnow
from app.detection.account_engine import evaluate, load_snapshot
from app.detection.account_rules import rule_catalogue
from app.detection.signals import combine, level_for
from app.models import (
    Alert,
    AuditEvent,
    Device,
    SecurityEvent,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    VerificationRequest,
)
from tests.conftest import ADMIN, LS_INVESTIGATOR, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded


def _quiet_account(db: Session, org_slug: str = "northbridge") -> StudentFinancialAccount:
    """An untouched, low-risk, on-campus synthetic account with an active card and spending history."""
    from app.models import Organization

    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    for acct in db.scalars(
        select(StudentFinancialAccount)
        .where(
            StudentFinancialAccount.organization_id == org.id,  # type: ignore[union-attr]
            StudentFinancialAccount.scenario_key.is_(None),
            StudentFinancialAccount.status == "active",
            StudentFinancialAccount.study_mode == "on_campus",
            StudentFinancialAccount.risk_level == "low",
        )
        .order_by(StudentFinancialAccount.reference)
    ):
        txns = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.account_id == acct.id))
        if txns >= 6:
            return acct
    raise AssertionError("no quiet account")


def _active_card(db: Session, acct: StudentFinancialAccount) -> StudentIDCard:
    return db.scalar(select(StudentIDCard).where(StudentIDCard.account_id == acct.id, StudentIDCard.status == "active"))  # type: ignore[return-value]


class TestSeededScenarios:
    def test_every_seeded_scenario_meets_its_expectation(self, as_user) -> None:  # type: ignore[no-untyped-def]
        checks = as_user(ADMIN).get("/api/v1/simulations/validation").json()
        assert {c["key"] for c in checks} >= {
            "lost_card",
            "password_reset",
            "account_takeover",
            "suspicious_transaction",
            "coordinated_ring",
            "control_new_phone",
            "control_travel",
            "control_forgot_password",
            "control_study_abroad",
            "control_saver",
        }
        assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]

    def test_legitimate_activity_is_not_flagged(self, db: Session) -> None:
        controls = db.scalars(
            select(StudentFinancialAccount).where(StudentFinancialAccount.scenario_key.like("control_%"))
        ).all()
        assert controls and all(a.risk_level == "low" and not a.sensitive_actions_restricted for a in controls)
        assert not db.scalar(select(Alert).where(Alert.account_id.in_([a.id for a in controls])))
        levels = db.scalars(select(StudentFinancialAccount.risk_level)).all()
        assert levels.count("low") / len(levels) > 0.9  # most students are simply students

    def test_no_raw_identifiers_or_payment_credentials_are_stored(self, db: Session) -> None:
        columns = {
            c
            for t in ("student_id_cards", "devices", "security_events", "transactions")
            for c in db.execute(text(f"PRAGMA table_info({t})")).scalars()
        }  # noqa: S608
        assert not columns & {"card_number", "pan", "pin", "cvv", "account_number", "ip_address", "device_id_raw"}
        tokens = db.scalars(select(StudentIDCard.card_token)).all()
        assert all(len(t) == 64 and "SBX" not in t for t in tokens)
        assert not db.scalar(select(Device).where(Device.device_token.like("seed-%")))


class TestAccountsApi:
    def test_list_detail_masking_and_location_gating(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        page = officer.get("/api/v1/accounts", params={"sort": "risk_score", "page_size": 5}).json()
        assert page["total"] > 100 and page["items"][0]["risk_level"] == "critical"
        row = page["items"][0]
        assert row["card"]["masked_number"].startswith("•••• ") and "*" in row["student"]["masked_name"]
        detail = officer.get(f"/api/v1/accounts/{row['id']}").json()
        assert detail["provider_mode"] == "sandbox" and detail["provider_account_handle"].startswith("ACC-")
        assert detail["assessment"]["signals"] and detail["registered_location"]
        assert not any(t["location_restricted"] for t in detail["transactions"])
        auditor = as_user(NB_AUDITOR).get(f"/api/v1/accounts/{row['id']}").json()
        assert auditor["registered_location"] is None and auditor["location_restricted"] is True
        assert all(t["location"] is None for t in auditor["transactions"])
        assert db.scalar(
            select(AuditEvent).where(AuditEvent.action == "account.view", AuditEvent.target_id == row["id"])
        )

    def test_filters_and_summary(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        restricted = client.get("/api/v1/accounts", params={"restricted": True}).json()
        assert restricted["total"] >= 7 and all(i["sensitive_actions_restricted"] for i in restricted["items"])
        pending = client.get("/api/v1/accounts", params={"verification_status": "pending"}).json()
        assert all(i["verification_status"] == "pending" for i in pending["items"])
        summary = client.get("/api/v1/accounts/summary").json()
        assert summary["restricted"] == restricted["total"] and float(summary["allocated_total"]) > 0

    def test_tenant_isolation(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        nb = _quiet_account(db)
        card = _active_card(db, nb)
        txn = db.scalar(select(Transaction).where(Transaction.account_id == nb.id))
        ls = as_user(LS_INVESTIGATOR)
        assert ls.get(f"/api/v1/accounts/{nb.id}").status_code == 404
        assert ls.get(f"/api/v1/cards/{card.id}").status_code == 404
        assert ls.get(f"/api/v1/transactions/{txn.id}").status_code == 404  # type: ignore[union-attr]
        for path in (
            "/api/v1/accounts",
            "/api/v1/cards",
            "/api/v1/transactions",
            "/api/v1/security/events",
            "/api/v1/verification-requests",
        ):
            items = ls.get(path, params={"page_size": 100}).json()["items"]
            assert items and {i["organization"]["slug"] for i in items} == {"lakeshore"}, path

    def test_read_only_roles_cannot_act(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        acct = _quiet_account(db)
        auditor = as_user(NB_AUDITOR)
        card = _active_card(db, acct)
        assert auditor.post(f"/api/v1/cards/{card.id}/report-lost", json={}).status_code == 403
        assert auditor.post(f"/api/v1/accounts/{acct.id}/restrict", json={"reason": "testing"}).status_code == 403
        investigator = as_user(
            NB_INVESTIGATOR
        )  # investigators restrict accounts but card operations sit with aid staff
        assert investigator.post(f"/api/v1/cards/{card.id}/report-lost", json={}).status_code == 403


class TestScenarioOneLostCard:
    def test_report_block_verify_replace_with_full_audit(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        acct = _quiet_account(db)
        card = _active_card(db, acct)
        officer = as_user(NB_OFFICER)
        res = officer.post(f"/api/v1/cards/{card.id}/report-lost", json={"channel": "phone", "note": "Lost on campus"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "blocked" and body["block_confirmation"].startswith("SBX-BLK-")
        account = officer.get(f"/api/v1/accounts/{acct.id}").json()
        assert account["status"] == "restricted" and account["sensitive_actions_restricted"]
        req = account["verification_requests"][0]
        assert req["trigger"] == "card_reported_lost" and req["pathway"] == "on_campus" and req["status"] == "pending"

        # No way to re-activate a blocked card; replacement waits for verified identity.
        assert officer.post(f"/api/v1/cards/{card.id}/block", json={"note": "again please"}).status_code == 409
        assert (
            officer.post(f"/api/v1/cards/{card.id}/request-replacement", json={"note": "Student asked"}).status_code
            == 200
        )
        assert officer.post(f"/api/v1/cards/{card.id}/issue-replacement").status_code == 409
        assert (
            officer.post(f"/api/v1/accounts/{acct.id}/lift-restriction", json={"reason": "please"}).status_code == 409
        )

        rid = req["id"]
        appointment = (utcnow() + timedelta(days=1)).isoformat()
        assert (
            officer.post(
                f"/api/v1/verification-requests/{rid}/decision",
                json={"outcome": "verified", "reason": "Too early to decide"},
            ).status_code
            == 409
        )
        assert (
            officer.post(
                f"/api/v1/verification-requests/{rid}/schedule", json={"appointment_at": appointment}
            ).status_code
            == 200
        )
        assert (
            officer.post(
                f"/api/v1/verification-requests/{rid}/checks",
                json={"step": "documents_checked", "result": "pass", "note": "State ID matches the record"},
            ).status_code
            == 200
        )
        decided = officer.post(
            f"/api/v1/verification-requests/{rid}/decision",
            json={"outcome": "verified", "reason": "Student verified in person with photo ID", "restore_access": True},
        )
        assert decided.status_code == 200 and decided.json()["access_restored"] is True
        steps = [e["step"] for e in decided.json()["events"]]
        assert (
            steps[:2] == ["created", "student_notified"] and "decision_verified" in steps and "access_restored" in steps
        )

        new = officer.post(f"/api/v1/cards/{card.id}/issue-replacement")
        assert new.status_code == 200 and new.json()["status"] == "active" and new.json()["id"] != str(card.id)
        db.expire_all()
        assert db.get(StudentIDCard, card.id).status == "replaced"  # type: ignore[union-attr]
        refreshed = db.get(StudentFinancialAccount, acct.id)
        assert refreshed.status == "active" and not refreshed.sensitive_actions_restricted  # type: ignore[union-attr]
        actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.organization_id == acct.organization_id)))
        assert {
            "card.report_lost",
            "card.block",
            "account.restrict",
            "verification_request.created",
            "verification_request.decision_verified",
            "account.restriction_lift",
            "card.replace",
        } <= actions

    def test_blocked_card_attempt_is_declined_and_alerted(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        res = as_user(NB_INVESTIGATOR).post("/api/v1/simulations/lost_card")
        assert res.status_code == 201, res.text
        out = res.json()
        assert out["accounts"][0]["risk_level"] in ("high", "critical")
        assert any("declined" in e for e in out["events"]) and out["verification_requests"]
        assert out["alerts"] and out["alerts"][0]["title"] == "Lost or stolen card used"


class TestOtherScenarios:
    def test_suspicious_password_reset_requests_step_up(self, as_user) -> None:  # type: ignore[no-untyped-def]
        out = as_user(NB_INVESTIGATOR).post("/api/v1/simulations/password_reset").json()
        acct = out["accounts"][0]
        assert acct["risk_level"] == "medium" and not acct["restricted"]  # proportionate: no automatic block
        assert any("step_up" in e for e in out["events"])
        assert out["alerts"][0]["title"] == "Suspicious password reset"

    def test_account_takeover_restricts_and_requests_verification(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        out = as_user(NB_INVESTIGATOR).post("/api/v1/simulations/account_takeover").json()
        acct = out["accounts"][0]
        assert acct["risk_level"] == "critical" and acct["restricted"] and out["verification_requests"]
        assert any("aid_redirect_requested → hold" in e for e in out["events"])
        assert any("money_transfer" in e and "declined" in e for e in out["events"])
        alert = db.scalar(select(Alert).where(Alert.account_id == uuid.UUID(acct["id"])))
        assert alert.category == "account_takeover" and alert.status == "verification_requested"  # type: ignore[union-attr]

    def test_suspicious_transaction_is_explained_not_auto_restricted(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        out = client.post("/api/v1/simulations/suspicious_transaction").json()
        assert out["accounts"][0]["risk_level"] in ("high", "critical") and not out["accounts"][0]["restricted"]
        alert = client.get(f"/api/v1/alerts/{out['alerts'][0]['id']}").json()
        codes = {s["code"] for s in alert["assessment"]["signals"]}
        assert {"IMPOSSIBLE_TRAVEL", "UNUSUAL_LOCATION", "SPENDING_SPIKE"} <= codes
        assert all("London" not in s["description"] for s in alert["assessment"]["signals"])  # no locations in text
        assert any(r["kind"] == "transaction" for r in alert["related"])

    def test_coordinated_ring_links_accounts_in_the_network(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        clusters = client.get("/api/v1/network/clusters").json()
        ring = [c for c in clusters if "account_device" in c["link_types"] or "redirect_destination" in c["link_types"]]
        assert ring and ring[0]["applications_other_institutions"] >= 1  # Lakeshore member: anonymous link only
        graph = client.get("/api/v1/network/graph", params={"cluster": ring[0]["id"]}).json()
        types = {n["type"] for n in graph["nodes"]}
        assert {"account", "card", "device", "destination", "external"} <= types


class TestProviderWebhooks:
    def _post(self, client, path: str, payload: dict, signature: str | None = None):  # type: ignore[no-untyped-def]
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "X-Provider-Signature": signature or sign(body)}
        return client.post(f"/api/v1/provider-events/{path}", content=body, headers=headers)

    def test_signature_idempotency_tokenization_and_decisions(self, client, db: Session) -> None:  # type: ignore[no-untyped-def]
        acct = _quiet_account(db)
        provider_id = f"SBX-ACCT-{acct.reference}"
        now = utcnow()
        event = {
            "provider_event_id": "evt-test-0001",
            "provider_account_id": provider_id,
            "event_type": "password_reset_requested",
            "outcome": "challenged",
            "occurred_at": now.isoformat(),
            "device_id": "raw-device-fingerprint-123",
            "ip": "203.0.113.9",
            "location_city": "Lisbon",
            "location_country": "PT",
        }
        assert self._post(client, "security", event, signature="sha256=bad").status_code == 401
        first = self._post(client, "security", event)
        assert first.status_code == 200, first.text
        assert first.json()["decision"] == "step_up" and not first.json()["duplicate"]
        again = self._post(client, "security", event)
        assert again.json()["duplicate"] and again.json()["reference"] == first.json()["reference"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(SecurityEvent.provider_event_id == "evt-test-0001")
            )
            == 1
        )
        stored = db.scalar(select(SecurityEvent).where(SecurityEvent.provider_event_id == "evt-test-0001"))
        assert "203.0.113.9" not in (stored.ip_token or "") and stored.device_id  # type: ignore[union-attr]
        device = db.get(Device, stored.device_id)  # type: ignore[union-attr]
        assert "raw-device" not in device.device_token  # type: ignore[union-attr]

        txn = {
            "provider_event_id": "evt-test-0002",
            "provider_account_id": provider_id,
            "amount": "12.50",
            "merchant_name": "Cardinal Coffee",
            "merchant_category": "dining",
            "channel": "card_present",
            "occurred_at": now.isoformat(),
            "location_city": acct.home_city,
            "location_country": "US",
        }
        res = self._post(client, "transactions", txn)
        assert res.status_code == 200 and res.json()["status"] == "approved"
        unknown = {**txn, "provider_event_id": "evt-test-0003", "provider_account_id": "SBX-ACCT-NOPE"}
        assert self._post(client, "transactions", unknown).status_code == 404
        future = {**txn, "provider_event_id": "evt-test-0004", "occurred_at": (now + timedelta(hours=2)).isoformat()}
        assert self._post(client, "transactions", future).status_code == 422


class TestVerificationRequests:
    def test_remote_pathway_methods_and_embassy_rule(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        from app.models import Organization

        nb = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
        acct = db.scalar(
            select(StudentFinancialAccount).where(
                StudentFinancialAccount.organization_id == nb.id,  # type: ignore[union-attr]
                StudentFinancialAccount.study_mode == "international",
                StudentFinancialAccount.scenario_key.is_(None),
                StudentFinancialAccount.home_country != "IN",
            )
        )
        officer = as_user(NB_OFFICER)
        res = officer.post(
            "/api/v1/verification-requests",
            json={"account_id": str(acct.id), "reason": "Unusual activity reported by the student"},
        )  # type: ignore[union-attr]
        assert res.status_code == 201, res.text
        req = res.json()
        assert req["pathway"] == "remote" and req["embassy_arrangement"] is None
        embassy = next(m for m in req["methods"] if m["method"] == "embassy_assisted")
        assert embassy["available"] is False
        assert (
            officer.post(
                f"/api/v1/verification-requests/{req['id']}/start", json={"method": "embassy_assisted"}
            ).status_code
            == 409
        )
        started = officer.post(f"/api/v1/verification-requests/{req['id']}/start", json={"method": "secure_video"})
        assert started.json()["status"] == "in_progress"
        officer.post(
            f"/api/v1/verification-requests/{req['id']}/checks",
            json={"step": "video_session_completed", "result": "fail", "note": "Person on video did not match ID"},
        )
        failed = officer.post(
            f"/api/v1/verification-requests/{req['id']}/decision",
            json={"outcome": "failed", "reason": "Could not confirm identity on video"},
        ).json()
        assert failed["status"] == "failed" and failed["decided_by"]
        assert db.scalar(select(StudentFinancialAccount.risk_score).where(StudentFinancialAccount.id == acct.id)) > 0  # type: ignore[union-attr]

    def test_auditor_cannot_decide(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        req = db.scalar(select(VerificationRequest).where(VerificationRequest.status == "pending"))
        res = as_user(NB_AUDITOR).post(
            f"/api/v1/verification-requests/{req.id}/decision",  # type: ignore[union-attr]
            json={"outcome": "verified", "reason": "auditors cannot decide"},
        )
        assert res.status_code == 403


class TestAlertsWorkflow:
    def test_assign_note_escalate_and_false_positive(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        items = client.get("/api/v1/alerts", params={"kind": "account", "status": ["open"]}).json()["items"]
        assert items and all(i["account_id"] for i in items)
        target = items[0]["id"]
        me = client.get("/api/v1/auth/me").json()["id"]
        assigned = client.post(f"/api/v1/alerts/{target}/assign", json={"assigned_to_id": me}).json()
        assert assigned["assigned_to"]["id"] == me
        noted = client.post(f"/api/v1/alerts/{target}/notes", json={"body": "Called the student."}).json()
        assert noted["notes"][-1]["body"] == "Called the student."
        assert client.patch(f"/api/v1/alerts/{target}", json={"action": "escalate"}).status_code == 422
        escalated = client.patch(f"/api/v1/alerts/{target}", json={"action": "escalate", "note": "Needs a case"}).json()
        assert escalated["status"] == "escalated"
        fp = client.patch(
            f"/api/v1/alerts/{target}", json={"action": "false_positive", "note": "Student was travelling"}
        )
        assert fp.json()["status"] == "false_positive"
        actions = [t["action"] for t in fp.json()["timeline"]]
        assert actions[0] == "alert.raised" and {"alert.assign", "alert.note_add", "alert.escalate"} <= set(actions)
        assert as_user(NB_AUDITOR).post(f"/api/v1/alerts/{target}/notes", json={"body": "nope"}).status_code == 403

    def test_request_verification_from_alert(self, as_user) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_INVESTIGATOR)
        alert = client.get(
            "/api/v1/alerts", params={"kind": "account", "status": ["open"], "severity": "medium"}
        ).json()
        target = (
            alert["items"]
            or client.get("/api/v1/alerts", params={"kind": "account", "status": ["open"]}).json()["items"]
        )[0]
        res = client.post(f"/api/v1/alerts/{target['id']}/request-verification", json={"reason": "Confirm identity"})
        assert res.status_code == 200 and res.json()["status"] == "verification_requested"
        assert any(r["kind"] == "verification_request" for r in res.json()["related"])


class TestDashboard:
    def test_metrics_come_from_scoped_records(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        overview = as_user(NB_INVESTIGATOR).get("/api/v1/dashboard/overview").json()
        metrics = {m["key"]: m["value"] for m in overview["metrics"]}
        from app.models import Organization

        nb = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
        expected = db.scalar(select(func.count()).select_from(Transaction).where(Transaction.organization_id == nb.id))  # type: ignore[union-attr]
        assert metrics["transactions"] == expected
        assert metrics["cards_blocked"] >= 1 and metrics["high_risk_alerts"] >= 1 and overview["synthetic"] is True
        assert len(overview["transaction_activity"]) == 31 and overview["recent_activity"]
        ls = {
            m["key"]: m["value"] for m in as_user(LS_INVESTIGATOR).get("/api/v1/dashboard/overview").json()["metrics"]
        }
        assert ls["transactions"] != metrics["transactions"]
        settings = as_user(NB_AUDITOR).get("/api/v1/system/settings").json()
        assert [b["level"] for b in settings["risk_bands"]] == ["low", "medium", "high", "critical"]
        assert settings["risk_bands"][0]["max"] < 30 and settings["risk_bands"][-1]["min"] == 80


class TestEngineRules:
    def test_single_weak_signals_stay_low(self) -> None:
        catalogue = rule_catalogue()
        for code in (
            "NEW_DEVICE",
            "UNUSUAL_LOGIN_LOCATION",
            "CARD_REPORTED_LOST",
            "NO_LOCAL_ACTIVITY",
            "HIGH_RISK_CATEGORY_NEW",
            "UNUSUAL_LOCATION",
        ):
            assert catalogue[code].weight < 0.3, code
        assert catalogue["NO_LOCAL_ACTIVITY"].context_only and catalogue["NO_LOCAL_ACTIVITY"].weight <= 0.02

    def test_combined_takeover_signals_escalate(self) -> None:
        from app.detection.signals import Signal

        def sig(code: str) -> Signal:
            r = rule_catalogue()[code]
            return Signal(r.code, r.category, r.severity, r.weight, r.title, r.description)

        assert level_for(combine([sig("NEW_DEVICE")])) == "low"
        combo = [
            sig(c)
            for c in (
                "NEW_DEVICE",
                "FAILED_LOGIN_BURST",
                "PASSWORD_RESET_UNFAMILIAR",
                "AID_REDIRECT_ATTEMPT",
                "TXN_AFTER_SUSPICIOUS_AUTH",
            )
        ]
        assert level_for(combine(combo)) == "critical"

    def test_weights_are_configurable(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "account_risk_weights", '{"NEW_DEVICE": 0.01, "BOGUS": 0.5}')
        rule_catalogue.cache_clear()
        try:
            assert rule_catalogue()["NEW_DEVICE"].weight == 0.01 and "BOGUS" not in rule_catalogue()
        finally:
            monkeypatch.undo()
            rule_catalogue.cache_clear()

    def test_saver_gets_context_only(self, db: Session) -> None:
        saver = db.scalar(
            select(StudentFinancialAccount).where(StudentFinancialAccount.scenario_key == "control_saver")
        )
        result = evaluate(load_snapshot(db, saver))  # type: ignore[arg-type]
        assert result.level == "low" and {s.code for s in result.signals} <= {"NO_LOCAL_ACTIVITY"}
        assert not result.needs_protection
