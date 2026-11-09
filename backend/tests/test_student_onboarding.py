from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.main import app
from app.models import Organization, Student, StudentInvitation, User
from tests.conftest import LS_INVESTIGATOR, NB_ADMIN, NB_OFFICER


def _unlinked_student(db: Session, slug: str = "northbridge") -> Student:
    org = db.scalar(select(Organization).where(Organization.slug == slug))
    assert org is not None
    student = db.scalar(
        select(Student)
        .outerjoin(User, User.student_id == Student.id)
        .where(Student.organization_id == org.id, User.id.is_(None))
    )
    assert student is not None
    return student


def _invite(as_user, db: Session, email: str = "new.student@northbridge.demo") -> tuple[object, str]:  # type: ignore[no-untyped-def]
    student = _unlinked_student(db)
    response = as_user(NB_ADMIN).post(f"/api/v1/students/{student.id}/invitation", json={"email": email})
    assert response.status_code == 201, response.text
    token = parse_qs(urlparse(response.json()["activation_url"]).query)["token"][0]
    return student, token


@pytest.mark.seeded
def test_authorized_invitation_and_activation_then_profile(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, token = _invite(as_user, db)
    activated = as_user(NB_ADMIN).post(
        "/api/v1/student-activation", json={"token": token, "password": "Strong!Activation2026"}
    )
    assert activated.status_code == 200 and activated.json()["activated"] is True
    portal = as_user("new.student@northbridge.demo", "Strong!Activation2026")
    profile = portal.get("/api/v1/student-profile/me")
    assert profile.status_code == 200 and profile.json()["student_ref"] == student.student_ref
    updated = portal.patch("/api/v1/student-profile/me", json={"state_of_residence": "CA", "biometric_consent": True})
    assert updated.status_code == 200 and updated.json()["state_of_residence"] == "CA"
    assert updated.json()["biometric_consent"] is True


@pytest.mark.seeded
def test_invitation_is_permissioned_and_tenant_scoped(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student = _unlinked_student(db)
    assert (
        as_user(NB_OFFICER)
        .post(f"/api/v1/students/{student.id}/invitation", json={"email": "x@northbridge.demo"})
        .status_code
        == 403
    )
    other = _unlinked_student(db, "lakeshore")
    assert (
        as_user(NB_ADMIN)
        .post(f"/api/v1/students/{other.id}/invitation", json={"email": "x@lakeshore.demo"})
        .status_code
        == 404
    )
    assert (
        as_user(LS_INVESTIGATOR)
        .post(f"/api/v1/students/{student.id}/invitation", json={"email": "x@northbridge.demo"})
        .status_code
        == 403
    )


@pytest.mark.seeded
def test_activation_rejects_expired_reused_and_invalid_tokens(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    _, expired_token = _invite(as_user, db, "expired.student@northbridge.demo")
    invitation = db.scalar(select(StudentInvitation).where(StudentInvitation.token_hash.is_not(None)))
    assert invitation is not None
    invitation.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert (
        as_user(NB_ADMIN)
        .post("/api/v1/student-activation", json={"token": expired_token, "password": "Strong!Activation2026"})
        .status_code
        == 401
    )
    assert (
        as_user(NB_ADMIN)
        .post("/api/v1/student-activation", json={"token": "x" * 43, "password": "Strong!Activation2026"})
        .status_code
        == 401
    )

    _, token = _invite(as_user, db, "used.student@northbridge.demo")
    first = as_user(NB_ADMIN).post(
        "/api/v1/student-activation", json={"token": token, "password": "Strong!Activation2026"}
    )
    assert first.status_code == 200
    assert (
        as_user(NB_ADMIN)
        .post("/api/v1/student-activation", json={"token": token, "password": "Strong!Activation2026"})
        .status_code
        == 401
    )

    _, revoked_token = _invite(as_user, db, "revoked.student@northbridge.demo")
    invitation = db.scalar(
        select(StudentInvitation).where(StudentInvitation.email == "revoked.student@northbridge.demo")
    )
    assert invitation is not None
    assert as_user(NB_ADMIN).post(f"/api/v1/student-invitations/{invitation.id}/revoke").status_code == 200
    assert (
        as_user(NB_ADMIN)
        .post("/api/v1/student-activation", json={"token": revoked_token, "password": "Strong!Activation2026"})
        .status_code
        == 401
    )


@pytest.mark.seeded
def test_duplicate_link_invalid_password_suspension_and_profile_authorization(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, token = _invite(as_user, db, "suspended.student@northbridge.demo")
    invalid = as_user(NB_ADMIN).post("/api/v1/student-activation", json={"token": token, "password": "short"})
    assert invalid.status_code == 422
    assert (
        as_user(NB_ADMIN)
        .post("/api/v1/student-activation", json={"token": token, "password": "Strong!Activation2026"})
        .status_code
        == 200
    )
    assert (
        as_user(NB_ADMIN)
        .post(f"/api/v1/students/{student.id}/invitation", json={"email": "again@northbridge.demo"})
        .status_code
        == 409
    )
    user = db.scalar(select(User).where(User.student_id == student.id))
    assert user is not None
    assert as_user(NB_OFFICER).get("/api/v1/student-profile/me").status_code == 403
    assert as_user(NB_ADMIN).patch(f"/api/v1/users/{user.id}", json={"is_active": False}).status_code == 200
    with TestClient(app) as client:
        client.headers["X-EduShield-Client"] = "test"
        assert (
            client.post(
                "/api/v1/auth/login",
                json={"email": "suspended.student@northbridge.demo", "password": "Strong!Activation2026"},
            ).status_code
            == 401
        )
