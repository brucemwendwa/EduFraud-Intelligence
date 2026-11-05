from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationStatusHistory, AuditEvent, FinancialAidApplication, User
from app.seed.base import DEMO_STUDENT_EMAIL
from tests.conftest import LS_INVESTIGATOR, NB_OFFICER

pytestmark = pytest.mark.seeded

_COMPLETE = {
    "award_year": "2026-2027",
    "dependency_status": "independent",
    "enrollment_intensity": "full_time",
    "program": "Computer Science",
    "requested_amount": "6500.00",
    "student_aid_index": 1200,
}


def _draft(as_user) -> tuple[object, dict]:  # type: ignore[no-untyped-def]
    student = as_user(DEMO_STUDENT_EMAIL)
    response = student.post("/api/v1/student-applications", json={})
    assert response.status_code == 201, response.text
    return student, response.json()


def test_student_can_create_save_submit_and_track_application(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, draft = _draft(as_user)
    assert draft["status"] == "draft" and draft["is_editable"] is True
    missing = student.post(f"/api/v1/student-applications/{draft['id']}/submit")
    assert missing.status_code == 422
    saved = student.patch(f"/api/v1/student-applications/{draft['id']}", json=_COMPLETE)
    assert saved.status_code == 200 and saved.json()["program"] == "Computer Science"
    submitted = student.post(f"/api/v1/student-applications/{draft['id']}/submit")
    assert submitted.status_code == 200 and submitted.json()["status"] == "submitted"
    assert submitted.json()["risk_level"] is not None
    assert [item["to_status"] for item in submitted.json()["history"]] == ["draft", "submitted"]
    assert student.patch(f"/api/v1/student-applications/{draft['id']}", json={"program": "Changed"}).status_code == 409
    assert student.post(f"/api/v1/student-applications/{draft['id']}/submit").status_code == 409
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "application.submit")) is not None


def test_student_ownership_staff_review_and_status_history(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, draft = _draft(as_user)
    assert student.patch(f"/api/v1/student-applications/{draft['id']}", json=_COMPLETE).status_code == 200
    assert student.post(f"/api/v1/student-applications/{draft['id']}/submit").status_code == 200
    assert student.patch(f"/api/v1/applications/{draft['id']}/review", json={}).status_code == 403

    officer = as_user(NB_OFFICER)
    queue = officer.get("/api/v1/applications", params={"q": draft["reference"]}).json()["items"]
    assert draft["id"] in {row["id"] for row in queue}
    assert officer.get(f"/api/v1/applications/{draft['id']}").status_code == 200
    reviewed = officer.patch(
        f"/api/v1/applications/{draft['id']}/review",
        json={
            "review_status": "in_review",
            "application_status": "additional_information_required",
            "note": "Please confirm enrollment.",
        },
    )
    assert reviewed.status_code == 200 and reviewed.json()["status"] == "additional_information_required"
    detail = student.get(f"/api/v1/student-applications/{draft['id']}").json()
    assert detail["is_editable"] is True
    assert "additional information" in detail["outstanding_requirements"][0]
    assert (
        student.patch(f"/api/v1/student-applications/{draft['id']}", json={"program": "Data Science"}).status_code
        == 200
    )
    assert student.post(f"/api/v1/student-applications/{draft['id']}/submit").json()["status"] == "submitted"
    history = db.scalars(
        select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == uuid.UUID(draft["id"]))
    ).all()
    assert {row.to_status for row in history} >= {"draft", "submitted", "additional_information_required"}


def test_student_cannot_access_other_student_or_other_tenant_application(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student = as_user(DEMO_STUDENT_EMAIL)
    owner = db.scalar(select(User).where(User.email == DEMO_STUDENT_EMAIL))
    assert owner is not None and owner.student_id is not None
    other = db.scalar(select(FinancialAidApplication).where(FinancialAidApplication.student_id != owner.student_id))
    assert other is not None
    assert student.get(f"/api/v1/student-applications/{other.id}").status_code == 404
    assert as_user(LS_INVESTIGATOR).get(f"/api/v1/applications/{other.id}").status_code == 404


def test_student_can_withdraw_but_cannot_change_final_staff_decision(as_user) -> None:  # type: ignore[no-untyped-def]
    student, draft = _draft(as_user)
    withdrawn = student.post(f"/api/v1/student-applications/{draft['id']}/withdraw")
    assert withdrawn.status_code == 200 and withdrawn.json()["status"] == "withdrawn"
    assert student.patch(f"/api/v1/student-applications/{draft['id']}", json=_COMPLETE).status_code == 409
