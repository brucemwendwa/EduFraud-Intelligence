"""User administration: institution-scoped, audited and closed to privilege escalation."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.types import utcnow
from app.models import AuditEvent, Organization, Role, StaffInvitation, User
from app.seed.base import DEMO_STUDENT_EMAIL
from tests.conftest import ADMIN, LS_INVESTIGATOR, NB_ADMIN, NB_AUDITOR, NB_OFFICER

PASSWORD = "Correct-Horse-2026!"
INVITE = {"email": "new.officer@northbridge.example", "full_name": "New Officer", "role_key": "financial_aid_officer"}


def _user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return user


def _staff(db: Session, email: str, role_key: str, org_slug: str = "northbridge") -> User:
    organization = db.scalar(select(Organization).where(Organization.slug == org_slug))
    role = db.scalar(select(Role).where(Role.key == role_key))
    assert organization is not None and role is not None
    user = User(
        email=email,
        full_name="Test Person",
        role_id=role.id,
        organization_id=organization.id,
        password_hash=hash_password(PASSWORD),
        is_demo=False,
    )
    db.add(user)
    db.commit()
    return user


def _token(invitation: dict) -> str:
    return invitation["activation_url"].split("token=")[1]


class TestDirectory:
    def test_directory_is_limited_to_the_institution(self, as_user) -> None:  # type: ignore[no-untyped-def]
        rows = as_user(NB_ADMIN).get("/api/v1/users", params={"page_size": 100}).json()["items"]
        assert rows and {row["organization"]["slug"] for row in rows} == {"northbridge"}

    def test_read_access_is_permission_gated(self, as_user) -> None:  # type: ignore[no-untyped-def]
        assert as_user(NB_AUDITOR).get("/api/v1/users").status_code == 200
        assert as_user(NB_OFFICER).get("/api/v1/users").status_code == 403

    def test_staff_can_be_listed_apart_from_students(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        rows = as_user(ADMIN).get("/api/v1/users", params={"kind": "staff", "page_size": 100}).json()["items"]
        assert all(row["role"]["key"] != "student" for row in rows)


class TestRoleChanges:
    @pytest.mark.parametrize("role", ["platform_admin", "student", "demo_presenter"])
    def test_restricted_roles_cannot_be_granted(self, as_user, db: Session, role: str) -> None:  # type: ignore[no-untyped-def]
        target = _staff(db, "target@northbridge.example", "auditor")
        response = as_user(NB_ADMIN).patch(f"/api/v1/users/{target.id}", json={"role_key": role})
        assert response.status_code == 403
        db.refresh(target)
        assert target.role.key == "auditor"

    def test_nobody_can_change_their_own_role_or_deactivate_themselves(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        me = _staff(db, "self@northbridge.example", "institution_admin")
        client = as_user("self@northbridge.example", PASSWORD)
        assert client.patch(f"/api/v1/users/{me.id}", json={"role_key": "auditor"}).status_code == 403
        assert client.patch(f"/api/v1/users/{me.id}", json={"is_active": False}).status_code == 403

    def test_a_student_account_cannot_become_staff(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        from app.models import Student

        organization = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
        assert organization is not None
        student_role = db.scalar(select(Role).where(Role.key == "student"))
        assert student_role is not None
        record = Student(
            organization_id=organization.id,
            student_ref="STU-99991",
            first_name="A",
            last_name="B",
            birth_year=2001,
            state_of_residence="OH",
        )
        db.add(record)
        db.flush()
        account = User(
            email="student.account@northbridge.example",
            full_name="Student Account",
            role_id=student_role.id,
            organization_id=organization.id,
            student_id=record.id,
            password_hash=hash_password(PASSWORD),
            is_demo=False,
        )
        db.add(account)
        db.commit()
        response = as_user(NB_ADMIN).patch(f"/api/v1/users/{account.id}", json={"role_key": "institution_admin"})
        assert response.status_code == 403

    def test_another_institutions_users_cannot_be_changed(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        outsider = _user(db, LS_INVESTIGATOR)
        assert as_user(NB_ADMIN).patch(f"/api/v1/users/{outsider.id}", json={"is_active": False}).status_code == 404

    def test_platform_administrators_are_out_of_reach(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        platform = _user(db, ADMIN)
        assert as_user(NB_ADMIN).patch(f"/api/v1/users/{platform.id}", json={"is_active": False}).status_code == 404

    def test_read_only_users_cannot_change_accounts(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        target = _staff(db, "target@northbridge.example", "auditor")
        assert as_user(NB_AUDITOR).patch(f"/api/v1/users/{target.id}", json={"is_active": False}).status_code == 403

    def test_last_administrator_cannot_be_removed(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        organization = "pinecrest"
        only_admin = _staff(db, "only.admin@pinecrest.example", "institution_admin", organization)
        pinecrest = db.scalar(select(Organization).where(Organization.slug == organization))
        assert pinecrest is not None
        platform = as_user(ADMIN, org=str(pinecrest.id))
        assert platform.patch(f"/api/v1/users/{only_admin.id}", json={"is_active": False}).status_code == 409
        assert platform.patch(f"/api/v1/users/{only_admin.id}", json={"role_key": "auditor"}).status_code == 409
        db.refresh(only_admin)
        assert only_admin.is_active and only_admin.role.key == "institution_admin"

    def test_account_changes_are_audited(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        target = _staff(db, "target@northbridge.example", "auditor")
        admin = as_user(NB_ADMIN)
        assert admin.patch(f"/api/v1/users/{target.id}", json={"role_key": "fraud_investigator"}).status_code == 200
        assert admin.patch(f"/api/v1/users/{target.id}", json={"is_active": False}).status_code == 200
        db.expire_all()
        actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.target_id == str(target.id))))
        assert {"user.role_change", "user.deactivate"} <= actions


class TestStaffInvitations:
    def test_invited_staff_choose_their_own_password(self, as_user, db: Session, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        created = as_user(NB_ADMIN).post("/api/v1/staff-invitations", json=INVITE)
        assert created.status_code == 201, created.text
        activation = client.post(
            "/api/v1/staff-activation", json={"token": _token(created.json()), "password": PASSWORD}
        )
        assert activation.status_code == 200, activation.text
        user = _user(db, INVITE["email"])
        assert user.role.key == "financial_aid_officer" and user.organization is not None
        assert user.organization.slug == "northbridge" and not user.is_demo
        officer = as_user(INVITE["email"], PASSWORD)
        assert officer.get("/api/v1/applications").status_code == 200

    def test_token_is_single_use_and_stored_hashed(self, as_user, db: Session, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        created = as_user(NB_ADMIN).post("/api/v1/staff-invitations", json=INVITE).json()
        stored = db.get(StaffInvitation, uuid.UUID(created["id"]))
        assert stored is not None and _token(created) not in stored.token_hash
        body = {"token": _token(created), "password": PASSWORD}
        assert client.post("/api/v1/staff-activation", json=body).status_code == 200
        assert client.post("/api/v1/staff-activation", json=body).status_code == 401

    def test_revoked_and_expired_invitations_cannot_activate(self, as_user, db: Session, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        admin = as_user(NB_ADMIN)
        revoked = admin.post("/api/v1/staff-invitations", json=INVITE).json()
        assert admin.post(f"/api/v1/staff-invitations/{revoked['id']}/revoke").status_code == 200
        body = {"token": _token(revoked), "password": PASSWORD}
        assert client.post("/api/v1/staff-activation", json=body).status_code == 401

        expired = admin.post("/api/v1/staff-invitations", json={**INVITE, "email": "late@northbridge.example"}).json()
        stored = db.get(StaffInvitation, uuid.UUID(expired["id"]))
        assert stored is not None
        stored.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
        body = {"token": _token(expired), "password": PASSWORD}
        assert client.post("/api/v1/staff-activation", json=body).status_code == 401

    def test_a_new_invitation_replaces_the_outstanding_one(self, as_user, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        admin = as_user(NB_ADMIN)
        first = admin.post("/api/v1/staff-invitations", json=INVITE).json()
        admin.post("/api/v1/staff-invitations", json=INVITE)
        body = {"token": _token(first), "password": PASSWORD}
        assert client.post("/api/v1/staff-activation", json=body).status_code == 401

    @pytest.mark.parametrize("role", ["platform_admin", "student", "demo_presenter"])
    def test_restricted_roles_cannot_be_invited(self, as_user, role: str) -> None:  # type: ignore[no-untyped-def]
        assert as_user(NB_ADMIN).post("/api/v1/staff-invitations", json={**INVITE, "role_key": role}).status_code == 403

    def test_existing_addresses_are_refused(self, as_user) -> None:  # type: ignore[no-untyped-def]
        response = as_user(NB_ADMIN).post("/api/v1/staff-invitations", json={**INVITE, "email": NB_OFFICER})
        assert response.status_code == 409

    def test_only_account_managers_can_invite(self, as_user) -> None:  # type: ignore[no-untyped-def]
        assert as_user(NB_AUDITOR).post("/api/v1/staff-invitations", json=INVITE).status_code == 403
        assert as_user(NB_OFFICER).post("/api/v1/staff-invitations", json=INVITE).status_code == 403

    def test_invitations_are_scoped_to_the_institution(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        created = as_user(NB_ADMIN).post("/api/v1/staff-invitations", json=INVITE).json()
        other_admin = _staff(db, "admin@lakeshore.example", "institution_admin", "lakeshore")
        del other_admin
        lakeshore = as_user("admin@lakeshore.example", PASSWORD)
        assert created["id"] not in {i["id"] for i in lakeshore.get("/api/v1/staff-invitations").json()}
        assert lakeshore.post(f"/api/v1/staff-invitations/{created['id']}/revoke").status_code == 404

    def test_platform_admin_must_choose_an_institution(self, as_user) -> None:  # type: ignore[no-untyped-def]
        assert as_user(ADMIN).post("/api/v1/staff-invitations", json=INVITE).status_code == 422

    def test_invitation_events_are_audited(self, as_user, db: Session, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        admin = as_user(NB_ADMIN)
        created = admin.post("/api/v1/staff-invitations", json=INVITE).json()
        client.post("/api/v1/staff-activation", json={"token": _token(created), "password": PASSWORD})
        db.expire_all()
        actions = set(db.scalars(select(AuditEvent.action)))
        assert {"user.invite", "user.activation"} <= actions


@pytest.mark.seeded
def test_students_are_refused_every_administrative_route(as_user) -> None:  # type: ignore[no-untyped-def]
    student = as_user(DEMO_STUDENT_EMAIL)
    assert student.get("/api/v1/users").status_code == 403
    assert student.get("/api/v1/staff-invitations").status_code == 403
    assert student.post("/api/v1/staff-invitations", json=INVITE).status_code == 403
