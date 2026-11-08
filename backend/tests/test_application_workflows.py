"""End-to-end API workflows across the student portal, staff review, evidence and dashboards."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, DetectionRun, FinancialAidApplication, User
from app.models.enums import RunStatus
from app.seed.base import DEMO_STUDENT_EMAIL
from app.services.detection_runs import execute_run
from tests.conftest import LS_INVESTIGATOR, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded

COMPLETE = {
    "award_year": "2026-2027",
    "dependency_status": "independent",
    "enrollment_intensity": "full_time",
    "program": "Computer Science",
    "requested_amount": "6500.00",
    "student_aid_index": 1200,
}


def _draft(student, **fields) -> dict:  # type: ignore[no-untyped-def]
    response = student.post("/api/v1/student-applications", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def _submitted(student) -> dict:  # type: ignore[no-untyped-def]
    draft = _draft(student, **COMPLETE)
    response = student.post(f"/api/v1/student-applications/{draft['id']}/submit")
    assert response.status_code == 200, response.text
    return response.json()


class TestDraftsDoNotBreakOtherWorkflows:
    """A draft has no submission data yet, so nothing downstream of submission may assume it does."""

    def test_empty_draft_does_not_block_another_submission(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        _draft(student)
        assert _submitted(student)["status"] == "submitted"

    def test_empty_draft_does_not_fail_a_detection_run(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        _draft(as_user(DEMO_STUDENT_EMAIL))
        run = DetectionRun(status=RunStatus.QUEUED, mode="inline", rules_version="test", model_version="test")
        db.add(run)
        db.commit()
        execute_run(run.id)
        db.refresh(run)
        assert run.status == RunStatus.COMPLETED, run.error

    def test_portal_summary_survives_an_empty_draft(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        _draft(student)
        assert student.get("/api/v1/student-portal/me").status_code == 200

    def test_withdrawn_draft_never_reaches_the_staff_queue(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        draft = _draft(student)
        assert student.post(f"/api/v1/student-applications/{draft['id']}/withdraw").status_code == 200

        officer = as_user(NB_OFFICER)
        queue = officer.get("/api/v1/applications", params={"status": "withdrawn", "page_size": 100})
        assert queue.status_code == 200, queue.text
        assert draft["id"] not in {row["id"] for row in queue.json()["items"]}
        assert officer.get(f"/api/v1/applications/{draft['id']}").status_code == 404


def _officer_review(officer, app_id: str, **body):  # type: ignore[no-untyped-def]
    payload = {"review_status": "in_review", "note": "Checked the submitted record.", **body}
    return officer.patch(f"/api/v1/applications/{app_id}/review", json=payload)


class TestStudentPortal:
    def test_fraud_risk_is_never_returned_to_the_student(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        app = _submitted(student)
        for response in (
            student.get(f"/api/v1/student-applications/{app['id']}"),
            student.get("/api/v1/student-applications"),
            student.get("/api/v1/student-portal/me"),
            student.get("/api/v1/student-portal/dashboard"),
        ):
            assert response.status_code == 200
            assert "risk" not in response.text.lower()

    def test_dashboard_reflects_only_this_students_records(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        owner = db.scalar(select(User).where(User.email == DEMO_STUDENT_EMAIL))
        before = student.get("/api/v1/student-portal/dashboard").json()["counts"]
        _draft(student)
        app = _submitted(student)
        body = student.get("/api/v1/student-portal/dashboard").json()

        assert body["profile"]["email"] == DEMO_STUDENT_EMAIL
        assert body["counts"]["total"] == before["total"] + 2
        assert body["counts"]["draft"] == before["draft"] + 1
        assert body["counts"]["submitted"] == before["submitted"] + 1
        own = set(
            db.scalars(
                select(FinancialAidApplication.reference).where(FinancialAidApplication.student_id == owner.student_id)
            )
        )
        assert {a["reference"] for a in body["applications"]} == own
        assert body["recent_activity"][0]["reference"] == app["reference"]
        assert body["recent_activity"][0]["title"] == "Application submitted"

    def test_staff_cannot_use_the_student_dashboard(self, as_user) -> None:  # type: ignore[no-untyped-def]
        assert as_user(NB_OFFICER).get("/api/v1/student-portal/dashboard").status_code == 403

    def test_information_request_and_response_round_trip(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        officer = as_user(NB_OFFICER)
        app = _submitted(student)

        refused = _officer_review(officer, app["id"], application_status="additional_information_required")
        assert refused.status_code == 422
        assert (
            _officer_review(
                officer,
                app["id"],
                application_status="additional_information_required",
                note="Internal: possible enrollment mismatch.",
                student_message="Please upload your enrollment letter.",
            ).status_code
            == 200
        )

        detail = student.get(f"/api/v1/student-applications/{app['id']}")
        assert detail.json()["status_message"]["message"] == "Please upload your enrollment letter."
        assert detail.json()["is_editable"] is True
        assert "possible enrollment mismatch" not in detail.text
        assert "financial_aid_officer" not in detail.text
        requests = student.get("/api/v1/student-portal/dashboard").json()["information_requests"]
        assert [r["message"] for r in requests] == ["Please upload your enrollment letter."]

        resubmitted = student.post(
            f"/api/v1/student-applications/{app['id']}/submit", json={"response_note": "Letter uploaded today."}
        )
        assert resubmitted.status_code == 200 and resubmitted.json()["status"] == "submitted"
        staff_history = officer.get(f"/api/v1/applications/{app['id']}").json()["status_history"]
        assert staff_history[0]["note"] == "Letter uploaded today."
        assert staff_history[0]["actor_role"] == "student"
        assert student.get("/api/v1/student-portal/dashboard").json()["information_requests"] == []

    def test_scoring_failure_does_not_lose_the_submission(  # type: ignore[no-untyped-def]
        self, as_user, db: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.api.v1 import student_applications

        class BrokenEngine:
            def __init__(self, _db: Session) -> None:
                raise RuntimeError("engine down")

        monkeypatch.setattr(student_applications, "DetectionEngine", BrokenEngine)
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        assert app["status"] == "submitted"
        stored = db.get(FinancialAidApplication, uuid.UUID(app["id"]))
        assert stored is not None and stored.risk_level is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "application.assessment_failed")) is not None


class TestStaffDecisions:
    def test_rejection_needs_a_reason_and_is_audited(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        officer = as_user(NB_OFFICER)
        app = _submitted(student)

        assert _officer_review(officer, app["id"], application_status="rejected").status_code == 422
        rejected = _officer_review(
            officer,
            app["id"],
            application_status="rejected",
            student_message="Your enrollment could not be verified for this term.",
        )
        assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"

        detail = student.get(f"/api/v1/student-applications/{app['id']}").json()
        assert detail["status_message"]["message"] == "Your enrollment could not be verified for this term."
        assert detail["is_editable"] is False and detail["is_withdrawable"] is False
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "application.status_change", AuditEvent.target_id == app["id"]
            )
        )
        assert event is not None and event.details["to_status"] == "rejected"

    def test_final_decisions_cannot_be_changed(self, as_user) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        assert _officer_review(officer, app["id"], application_status="approved").status_code == 200
        assert _officer_review(officer, app["id"], application_status="in_review").status_code == 409
        assert officer.get(f"/api/v1/applications/{app['id']}").json()["allowed_status_changes"] == []

    def test_allowed_status_changes_follow_the_lifecycle(self, as_user) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        allowed = officer.get(f"/api/v1/applications/{app['id']}").json()["allowed_status_changes"]
        assert set(allowed) == {"additional_information_required", "approved", "in_review", "on_hold", "rejected"}

    def test_review_without_status_change_stays_off_the_student_timeline(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        officer = as_user(NB_OFFICER)
        app = _submitted(student)
        assert _officer_review(officer, app["id"], note="Internal check of the shared address.").status_code == 200

        staff = officer.get(f"/api/v1/applications/{app['id']}").json()["status_history"]
        assert staff[0]["note"] == "Internal check of the shared address."
        assert staff[0]["actor_name"] == "Elena Torres"
        detail = student.get(f"/api/v1/student-applications/{app['id']}")
        assert "shared address" not in detail.text
        assert len(detail.json()["history"]) == 2

    def test_permissions_and_tenancy_are_enforced_by_the_api(self, as_user) -> None:  # type: ignore[no-untyped-def]
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        assert _officer_review(as_user(NB_AUDITOR), app["id"]).status_code == 403
        assert _officer_review(as_user(LS_INVESTIGATOR), app["id"]).status_code == 404

    def test_unsubmitted_drafts_are_invisible_to_staff_actions(self, as_user) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        draft = _draft(as_user(DEMO_STUDENT_EMAIL))
        assert _officer_review(officer, draft["id"]).status_code == 404
        assert officer.get(f"/api/v1/applications/{draft['id']}/documents").status_code == 404
        assert as_user(NB_INVESTIGATOR).post(f"/api/v1/applications/{draft['id']}/assess").status_code == 404

    def test_awaiting_review_queue(self, as_user) -> None:  # type: ignore[no-untyped-def]
        officer = as_user(NB_OFFICER)
        app = _submitted(as_user(DEMO_STUDENT_EMAIL))
        queue = officer.get("/api/v1/applications", params={"queue": "awaiting_review", "page_size": 100}).json()
        assert {row["status"] for row in queue["items"]} <= {"submitted", "received"}
        assert (
            officer.get("/api/v1/applications", params={"queue": "awaiting_review", "q": app["reference"]}).json()[
                "total"
            ]
            == 1
        )
        _officer_review(officer, app["id"], application_status="in_review")
        assert (
            officer.get("/api/v1/applications", params={"queue": "awaiting_review", "q": app["reference"]}).json()[
                "total"
            ]
            == 0
        )
