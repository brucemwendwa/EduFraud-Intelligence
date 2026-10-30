from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.types import utcnow
from app.main import app
from app.models import AuditEvent, User
from app.seed.base import DEMO_PASSWORD
from tests.conftest import ADMIN, NB_INVESTIGATOR


def _client() -> TestClient:
    c = TestClient(app)
    c.headers["X-EduShield-Client"] = "test"
    return c


def test_login_sets_hardened_session_cookie_and_returns_profile(engine) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        res = c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": DEMO_PASSWORD})
        assert res.status_code == 200
        body = res.json()
        assert body["role"]["key"] == "fraud_investigator"
        assert body["organization"]["slug"] == "northbridge"
        assert "cases:resolve" in body["permissions"] and "audit:read" not in body["permissions"]
        cookie = res.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
        assert "password" not in res.text

        assert c.get("/api/v1/auth/me").json()["email"] == NB_INVESTIGATOR
        assert c.post("/api/v1/auth/logout").status_code == 204
        assert c.get("/api/v1/auth/me").status_code == 401


def test_invalid_credentials_share_one_generic_message(engine) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        wrong = c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": "nope"})
        unknown = c.post("/api/v1/auth/login", json={"email": "ghost@nowhere.demo", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"] == "Invalid email or password."


def test_account_locks_after_repeated_failures(engine, db: Session) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        for _ in range(get_settings().login_max_attempts):
            c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": "wrong-password"})
        locked = c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": DEMO_PASSWORD})
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "account_locked"
    actions = db.scalars(select(AuditEvent.action).where(AuditEvent.actor_email == NB_INVESTIGATOR)).all()
    assert "auth.lockout" in actions


def test_failed_login_never_records_the_attempted_password(engine, db: Session) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": "Sup3r-Secret-Guess!"})
    for event in db.scalars(select(AuditEvent)):
        assert "Sup3r-Secret-Guess!" not in str(event.details)


def test_bearer_token_flow_for_api_clients(engine) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        tok = c.post("/api/v1/auth/token", data={"username": ADMIN, "password": DEMO_PASSWORD}).json()
    with TestClient(app) as api:
        me = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert me.status_code == 200 and me.json()["is_platform_admin"] is True
        bad = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}x"})
        assert bad.status_code == 401


def test_password_change_revokes_previously_issued_tokens(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    c = as_user(NB_INVESTIGATOR)
    user = db.scalar(select(User).where(User.email == NB_INVESTIGATOR))
    assert user is not None
    user.password_changed_at = utcnow() + timedelta(seconds=5)
    db.commit()
    assert c.get("/api/v1/auth/me").status_code == 401


def test_password_policy_is_enforced_for_new_users(as_user) -> None:  # type: ignore[no-untyped-def]
    admin = as_user(ADMIN)
    res = admin.post(
        "/api/v1/users",
        json={
            "email": "weak@northbridge.demo",
            "full_name": "Weak Pw",
            "role_key": "auditor",
            "organization_id": None,
            "password": "alllowercase",
        },
    )
    assert res.status_code == 422


def test_demo_accounts_are_listed_without_secrets_and_disabled_outside_demo_mode(engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        accounts = c.get("/api/v1/auth/demo-accounts").json()
        assert {a["role_key"] for a in accounts} >= {"platform_admin", "fraud_investigator", "auditor"}
        assert all("password" not in a for a in accounts)

        monkeypatch.setattr(get_settings(), "demo_mode", False)
        assert c.get("/api/v1/auth/demo-accounts").json() == []
        res = c.post("/api/v1/auth/login", json={"email": NB_INVESTIGATOR, "password": DEMO_PASSWORD})
        assert res.status_code == 401


def test_login_payload_is_validated(engine) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        res = c.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "email"
    assert "not-an-email" not in res.text  # submitted values are never echoed back
