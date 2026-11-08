from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.types import utcnow
from app.main import app
from app.models import AuditEvent, User
from app.seed.base import DEMO_PASSWORD, DEMO_PRESENTER_EMAIL, DEMO_STUDENT_EMAIL
from tests.conftest import ADMIN, NB_INVESTIGATOR


def _client() -> TestClient:
    c = TestClient(app)
    c.headers["X-EduShield-Client"] = "test"
    return c


_PRODUCTION_SETTINGS = {
    "env": "production",
    "database_url": "postgresql+psycopg://edushield:password@db.example/edushield",
    "jwt_secret": "production-jwt-secret",
    "tokenization_key": "production-tokenization-key",
    "provider_webhook_secret": "production-webhook-secret",
    "data_encryption_key": "not-used-during-settings-validation",
    "email_provider": "smtp",
    "smtp_host": "smtp.example",
    "smtp_username": "edushield-test",
    "smtp_password": "not-a-real-password",
    "s3_bucket_name": "edushield-private-test",
    "s3_access_key_id": "test-access-key",
    "s3_secret_access_key": "not-a-real-storage-secret",
    "email_from": "EduShield AI <no-reply@mail.example.edu>",
    "student_activation_base_url": "https://aid.example.edu/activate",
}


def test_demo_mode_defaults_to_disabled_without_environment_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DEMO_MODE", raising=False)
    assert Settings(_env_file=None).demo_mode is False


def test_demo_mode_can_be_explicitly_enabled_for_development() -> None:
    assert Settings(_env_file=None, env="development", demo_mode=True).demo_mode is True


def test_production_rejects_demo_mode() -> None:
    with pytest.raises(ValidationError, match="DEMO_MODE must be false in production"):
        Settings(_env_file=None, demo_mode=True, **_PRODUCTION_SETTINGS)


def test_production_configuration_is_valid_when_demo_mode_is_disabled() -> None:
    settings = Settings(_env_file=None, demo_mode=False, **_PRODUCTION_SETTINGS)
    assert settings.env == "production" and settings.demo_mode is False


def test_production_rejects_unconfigured_student_invitation_delivery() -> None:
    config = {**_PRODUCTION_SETTINGS, "email_provider": "development", "smtp_host": None}
    with pytest.raises(ValidationError, match="SMTP email delivery"):
        Settings(_env_file=None, demo_mode=False, **config)


def test_production_rejects_unconfigured_document_storage() -> None:
    config = {**_PRODUCTION_SETTINGS, "s3_bucket_name": None}
    with pytest.raises(ValidationError, match="S3 document storage"):
        Settings(_env_file=None, demo_mode=False, **config)


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


def test_demo_login_uses_a_restricted_synthetic_session(engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        res = c.post("/api/v1/auth/demo-login")
        assert res.status_code == 200
        body = res.json()
        assert body["email"] == DEMO_PRESENTER_EMAIL and body["is_demo"] is True
        assert "audit:read" in body["permissions"] and "pii:reveal" not in body["permissions"]
        assert "disbursements:hold" not in body["permissions"] and body["is_platform_admin"] is False
        assert "httponly" in res.headers["set-cookie"].lower()
        monkeypatch.setattr(get_settings(), "demo_mode", False)
        disabled = c.post("/api/v1/auth/demo-login")
        assert disabled.status_code == 401
        assert disabled.json()["error"]["message"] == "Invalid email or password."
        # Disabling demo mode also invalidates an already-issued demo session.
        assert c.get("/api/v1/auth/me").status_code == 401


def test_login_payload_is_validated(engine) -> None:  # type: ignore[no-untyped-def]
    with _client() as c:
        res = c.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["field"] == "email"
    assert "not-an-email" not in res.text  # submitted values are never echoed back


@pytest.mark.seeded
def test_synthetic_student_can_only_access_own_portal(as_user) -> None:  # type: ignore[no-untyped-def]
    student = as_user(DEMO_STUDENT_EMAIL)
    portal = student.get("/api/v1/student-portal/me")
    assert portal.status_code == 200 and portal.json()["applications"]
    assert student.get("/api/v1/applications").status_code == 403
    with _client() as anonymous:
        assert anonymous.get("/api/v1/student-portal/me").status_code == 401


def _hosted_settings(**overrides):  # type: ignore[no-untyped-def]
    from cryptography.fernet import Fernet

    from app.core.config import Settings

    values = {
        "database_url": "postgresql+psycopg://u:p@db/x",
        "jwt_secret": "a-unique-jwt-secret-for-this-test-only-000000",
        "tokenization_key": "a-unique-tokenization-key-for-this-test-only",
        "provider_webhook_secret": "a-unique-webhook-secret-for-this-test-only",
        "data_encryption_key": Fernet.generate_key().decode(),
        "cors_origins": "https://app.example.edu",
        "_env_file": None,
        **overrides,
    }
    return Settings(**values)


def test_demo_environment_is_hardened_but_allows_demo_sign_in() -> None:
    settings = _hosted_settings(env="demo", demo_mode=True)
    assert settings.is_hardened and not settings.is_production


def test_demo_environment_still_requires_real_secrets_and_postgres() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        _hosted_settings(env="demo", jwt_secret="change-me-jwt-secret-for-local-development-only")
    with pytest.raises(ValueError, match="PostgreSQL"):
        _hosted_settings(env="demo", database_url="sqlite:///x.db")


def test_production_refuses_wildcard_cors_and_plain_storage_traffic() -> None:
    complete = {
        "env": "production",
        "email_provider": "smtp",
        "smtp_host": "smtp.example.edu",
        "smtp_username": "u",
        "smtp_password": "p",
        "s3_bucket_name": "b",
        "s3_access_key_id": "k",
        "s3_secret_access_key": "s",
        "demo_mode": False,
        "email_from": "EduShield AI <no-reply@mail.example.edu>",
        "student_activation_base_url": "https://aid.example.edu/activate",
    }
    assert _hosted_settings(**complete).is_production
    with pytest.raises(ValueError, match="exact origins"):
        _hosted_settings(**complete, cors_origins="*")
    with pytest.raises(ValueError, match="TLS"):
        _hosted_settings(**complete, s3_use_tls=False)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://u:p@db.internal:5432/x", "postgresql+psycopg://u:p@db.internal:5432/x"),
        ("postgres://u:p@db.internal:5432/x", "postgresql+psycopg://u:p@db.internal:5432/x"),
        ("postgresql+psycopg://u:p@db/x", "postgresql+psycopg://u:p@db/x"),
        ("sqlite:///./var/x.db", "sqlite:///./var/x.db"),
    ],
)
def test_platform_database_urls_use_the_installed_driver(url: str, expected: str) -> None:
    assert Settings(_env_file=None, database_url=url).database_url == expected


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"student_activation_base_url": "http://localhost:5173/activate"}, "STUDENT_ACTIVATION_BASE_URL"),
        ({"public_url": "http://aid.example.edu"}, "PUBLIC_URL"),
        ({"email_from": "no-reply@edushield.local"}, "EMAIL_FROM"),
    ],
)
def test_production_refuses_links_and_senders_that_cannot_work(override: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, demo_mode=False, **{**_PRODUCTION_SETTINGS, **override})
