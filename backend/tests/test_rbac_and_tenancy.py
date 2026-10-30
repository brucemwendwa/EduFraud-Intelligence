from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import ROLE_BY_KEY, P
from app.models import AuditEvent, Organization, User
from tests.conftest import ADMIN, LS_INVESTIGATOR, NB_ADMIN, NB_AUDITOR, NB_INVESTIGATOR, NB_OFFICER

NEW_USER = {
    "email": "new.person@northbridge.demo",
    "full_name": "New Person",
    "role_key": "auditor",
    "password": "Str0ng!Passphrase",
}


def _org_id(db: Session, slug: str) -> str:
    return str(db.scalar(select(Organization.id).where(Organization.slug == slug)))


class TestPermissionCatalogue:
    def test_frontend_permission_keys_match_backend(self) -> None:
        ts = (Path(__file__).resolve().parents[2] / "frontend/src/lib/permissions.ts").read_text()
        frontend = set(re.findall(r":\s*'([a-z_]+:[a-z_]+)'", ts))
        assert frontend == {p.value for p in P}

    def test_auditor_is_read_only(self) -> None:
        writes = {p for p in ROLE_BY_KEY["auditor"].permissions if not p.value.endswith(":read")}
        assert writes == set()

    def test_only_platform_role_manages_institutions(self) -> None:
        holders = {k for k, r in ROLE_BY_KEY.items() if P.ORGS_MANAGE in r.permissions}
        assert holders == {"platform_admin"}


@pytest.mark.parametrize(
    ("email", "expected"),
    [(ADMIN, 200), (NB_ADMIN, 200), (NB_AUDITOR, 200), (NB_INVESTIGATOR, 403), (NB_OFFICER, 403)],
)
def test_audit_trail_access_matrix(as_user, email: str, expected: int) -> None:  # type: ignore[no-untyped-def]
    assert as_user(email).get("/api/v1/audit/events").status_code == expected


def test_denied_access_is_itself_audited(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    res = as_user(NB_AUDITOR).post("/api/v1/users", json=NEW_USER)
    assert res.status_code == 403
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "access.denied"))
    assert event is not None and event.outcome == "denied"
    assert event.details["missing"] == ["users:manage"]


def test_institution_admin_cannot_grant_platform_role(as_user) -> None:  # type: ignore[no-untyped-def]
    res = as_user(NB_ADMIN).post("/api/v1/users", json={**NEW_USER, "role_key": "platform_admin"})
    assert res.status_code == 403


def test_institution_admin_creates_users_only_in_own_institution(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    res = as_user(NB_ADMIN).post("/api/v1/users", json={**NEW_USER, "organization_id": _org_id(db, "lakeshore")})
    assert res.status_code == 201
    assert res.json()["organization"]["slug"] == "northbridge"


def test_role_change_is_audited_as_permission_change(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    admin = as_user(NB_ADMIN)
    created = admin.post("/api/v1/users", json=NEW_USER).json()
    res = admin.patch(f"/api/v1/users/{created['id']}", json={"role_key": "fraud_investigator"})
    assert res.status_code == 200 and res.json()["role"]["key"] == "fraud_investigator"
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.role_change"))
    assert event is not None and event.category == "permission"
    assert event.details == {"from": "auditor", "to": "fraud_investigator"}


def test_users_cannot_change_their_own_role(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    me = db.scalar(select(User).where(User.email == NB_ADMIN))
    res = as_user(NB_ADMIN).patch(f"/api/v1/users/{me.id}", json={"role_key": "auditor"})  # type: ignore[union-attr]
    assert res.status_code == 403


class TestTenantIsolation:
    def test_institution_users_only_see_their_institution(self, as_user) -> None:  # type: ignore[no-untyped-def]
        orgs = as_user(LS_INVESTIGATOR).get("/api/v1/organizations").json()
        assert [o["slug"] for o in orgs] == ["lakeshore"]

        users = as_user(NB_ADMIN).get("/api/v1/users", params={"page_size": 100}).json()["items"]
        assert users and all(u["organization"]["slug"] == "northbridge" for u in users)

    def test_cross_tenant_record_access_returns_404(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        lakeshore_user = db.scalar(select(User).where(User.email == LS_INVESTIGATOR))
        res = as_user(NB_ADMIN).patch(f"/api/v1/users/{lakeshore_user.id}", json={"title": "Hijacked"})  # type: ignore[union-attr]
        assert res.status_code == 404

    def test_institution_users_cannot_switch_scope_with_header(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        client = as_user(NB_ADMIN, org=_org_id(db, "lakeshore"))
        users = client.get("/api/v1/users", params={"page_size": 100}).json()["items"]
        assert all(u["organization"]["slug"] == "northbridge" for u in users)

    def test_platform_admin_scopes_by_header(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        everyone = as_user(ADMIN).get("/api/v1/users", params={"page_size": 100}).json()
        scoped = as_user(ADMIN, org=_org_id(db, "lakeshore")).get("/api/v1/users").json()
        assert everyone["total"] > scoped["total"]
        assert {u["organization"]["slug"] for u in scoped["items"]} == {"lakeshore"}

    def test_unknown_scope_header_is_rejected(self, as_user) -> None:  # type: ignore[no-untyped-def]
        res = as_user(ADMIN, org="00000000-0000-0000-0000-000000000000").get("/api/v1/users")
        assert res.status_code == 404
