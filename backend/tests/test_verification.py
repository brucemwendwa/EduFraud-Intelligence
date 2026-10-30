"""Phase 7: simulated biometric provider, verification workflows, consent and privacy guarantees."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from app.biometrics.provider import VerificationRequest
from app.biometrics.simulated import TEST_SAMPLES, SimulatedBiometricProvider
from app.models import Alert, AuditEvent, FinancialAidApplication, IdentityVerification
from app.services.verification import decide
from tests.conftest import NB_AUDITOR, NB_INVESTIGATOR


def _verify(sample: str, student_ref: str = "STU-00001"):  # type: ignore[no-untyped-def]
    return SimulatedBiometricProvider().verify(
        VerificationRequest(
            biometric_reference_id="sim-tpl-x", sample_handle=sample, student_ref=student_ref, trigger="t"
        )
    )


class TestSimulatedProvider:
    @pytest.mark.parametrize(
        ("sample", "outcome"),
        [
            ("enrolled_student", "passed"),
            ("different_person", "failed"),
            ("impostor_screen_replay", "failed"),
            ("printed_photo", "failed"),
            ("altered_document", "failed"),
            ("unreadable_document", "review"),
        ],
    )
    def test_each_test_sample_produces_its_documented_outcome(self, sample: str, outcome: str) -> None:
        result = _verify(sample)
        assert decide(result)[0].value == outcome
        assert result.mode == "simulation"
        assert [s.stage for s in result.stages] == ["document", "face_match", "liveness", "presentation_attack"]

    def test_results_are_deterministic_per_student(self) -> None:
        assert _verify("different_person").face_match_score == _verify("different_person").face_match_score
        assert (
            _verify("different_person", "STU-1").face_match_score
            != _verify("different_person", "STU-2").face_match_score
        )

    def test_presentation_attacks_are_reported_with_type(self) -> None:
        result = _verify("printed_photo")
        assert result.pad_result == "attack_detected" and result.pad_attack_type == "printed_photo"
        assert any("Presentation attack" in i for i in decide(result)[1])

    def test_every_sample_is_documented(self) -> None:
        assert all(s.label and s.description and s.expected for s in TEST_SAMPLES.values())


class TestPrivacy:
    def test_verification_table_has_no_image_or_template_columns(self, engine: Engine) -> None:
        columns = {c["name"] for c in inspect(engine).get_columns("identity_verifications")}
        assert not {c for c in columns if any(w in c for w in ("image", "photo", "template", "selfie", "blob"))}


def _consented(db: Session) -> FinancialAidApplication:
    for app in db.scalars(
        select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "control_bank_change")
    ):
        assert app.student.biometric_consent
        return app
    raise AssertionError("no consented student")


def _no_consent(db: Session) -> FinancialAidApplication:
    app = db.scalar(select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "duplicate_identity"))
    assert app is not None and not app.student.biometric_consent
    return app


@pytest.mark.seeded
class TestVerificationApi:
    def test_seeded_impersonation_attempt_is_detected_end_to_end(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = db.scalar(
            select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "identity_impersonation")
        )
        assert app is not None and app.risk_level == "critical" and app.verification_status == "failed"
        alert = db.scalar(select(Alert).where(Alert.application_id == app.id))
        assert alert is not None and alert.title == "Possible identity impersonation" and alert.verification_id
        checks = as_user("admin@edushield.demo").get("/api/v1/detection/scenario-validation").json()
        impersonation = next(c for c in checks if c["scenario"] == "identity_impersonation")
        assert impersonation["passed"] and "FACE_MISMATCH" in impersonation["observed_signals"]

    def test_failed_biometric_raises_risk_and_is_audited(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _consented(db)
        before = app.risk_score
        res = as_user("officer@pinecrest.demo").post(
            "/api/v1/verifications",
            json={"application_id": str(app.id), "trigger": "account_recovery", "sample_key": "different_person"},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["status"] == "failed" and body["provider_mode"] == "simulation"
        assert body["stages"][1]["stage"] == "face_match" and body["stages"][1]["outcome"] == "fail"
        assert "Do not complete the account recovery" in body["recommended_action"]
        assert body["resulting_risk_score"] > (before or 0)
        db.expire_all()
        assert db.get(FinancialAidApplication, app.id).verification_status == "failed"  # type: ignore[union-attr]
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "verification.biometric"))
        assert event is not None and event.outcome == "failure" and event.category == "verification"

    def test_biometrics_require_consent(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _no_consent(db)
        res = as_user(NB_INVESTIGATOR).post(
            "/api/v1/verifications",
            json={"application_id": str(app.id), "trigger": "risk_review", "sample_key": "enrolled_student"},
        )
        assert res.status_code == 409 and res.json()["error"]["code"] == "biometric_consent_required"

    def test_alternative_verification_is_recorded_with_notes(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _no_consent(db)
        url = "/api/v1/verifications/alternative"
        payload = {
            "application_id": str(app.id),
            "trigger": "risk_review",
            "method": "in_person_id_check",
            "outcome": "failed",
        }
        assert as_user(NB_INVESTIGATOR).post(url, json={**payload, "notes": "short"}).status_code == 422
        assert (
            as_user(NB_AUDITOR).post(url, json={**payload, "notes": "Auditors cannot record this"}).status_code == 403
        )
        res = as_user(NB_INVESTIGATOR).post(
            url, json={**payload, "notes": "Presented ID did not match the person at desk"}
        )
        assert res.status_code == 201
        assert res.json()["provider_mode"] == "manual" and res.json()["initiated_by"] == "Marcus Bell"

    def test_unknown_sample_and_cross_tenant_requests_are_rejected(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        app = _consented(db)  # Pinecrest
        bad = {"application_id": str(app.id), "trigger": "risk_review", "sample_key": "deepfake_9000"}
        assert as_user("officer@pinecrest.demo").post("/api/v1/verifications", json=bad).status_code == 422
        ok = {**bad, "sample_key": "enrolled_student"}
        assert as_user(NB_INVESTIGATOR).post("/api/v1/verifications", json=ok).status_code == 404

    def test_history_and_stats(self, as_user) -> None:  # type: ignore[no-untyped-def]
        c = as_user(NB_INVESTIGATOR)
        history = c.get("/api/v1/verifications", params={"status": "failed"}).json()
        assert history["total"] >= 1 and all(v["status"] == "failed" for v in history["items"])
        stats = c.get("/api/v1/verifications/stats").json()
        assert stats["total"] == stats["passed"] + stats["failed"] + stats["review"]
        assert stats["attacks_detected"] >= 1
        provider = c.get("/api/v1/verifications/provider").json()
        assert provider["mode"] == "simulation" and "SIMULATED" in provider["disclaimer"]

    def test_no_image_payloads_are_persisted(self, engine: Engine) -> None:
        raw = Path(engine.url.database).read_bytes()  # type: ignore[arg-type]
        assert b"/9j/" not in raw and b"iVBORw0KGgo" not in raw  # JPEG / PNG base64 signatures


def test_verification_rows_link_to_applications(db: Session) -> None:
    assert db.scalar(select(IdentityVerification).where(IdentityVerification.application_id.is_(None))) is None
