"""The account lifecycle: sessions, password recovery, invitations, abuse limits and role boundaries."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter
from app.core.security import hash_password
from app.db.types import utcnow
from app.main import app
from app.models import FinancialAidApplication, Organization, PasswordResetToken, RevokedSession, Role, User
from app.seed.base import DEMO_PASSWORD, DEMO_STUDENT_EMAIL
from app.services.account_maintenance import purge_expired_credentials
from tests.conftest import LS_INVESTIGATOR, NB_ADMIN, NB_AUDITOR, NB_OFFICER

PASSWORD = "Correct-Horse-2026!"
NEW_PASSWORD = "Different-Battery-2027!"
HEADERS = {"X-EduShield-Client": "test"}
REAL_EMAIL = "real.staff@northbridge.example"


def _bearer(client: TestClient, email: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    response = client.post("/api/v1/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def real_user(db: Session, engine) -> User:  # type: ignore[no-untyped-def]
    organization = db.scalar(select(Organization).where(Organization.slug == "northbridge"))
    role = db.scalar(select(Role).where(Role.key == "financial_aid_officer"))
    assert organization is not None and role is not None
    user = User(
        email=REAL_EMAIL,
        full_name="Real Staff",
        role_id=role.id,
        organization_id=organization.id,
        password_hash=hash_password(PASSWORD),
        is_demo=False,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def sent_links(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    from app.api.v1 import auth

    links: list[tuple[str, str]] = []

    class Recorder:
        def send(self, *, recipient: str, content) -> None:  # type: ignore[no-untyped-def]
            links.append((recipient, content.text))

    monkeypatch.setattr(auth, "get_mailer", lambda _settings=None: Recorder())
    return links


def _token_from(text: str) -> str:
    return text.split("token=")[1].split()[0]


class TestSessions:
    def test_sign_out_ends_the_session_on_the_server(self, client: TestClient, db: Session) -> None:
        headers = _bearer(client, NB_OFFICER)
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        assert db.scalar(select(RevokedSession)) is not None

    def test_a_copied_browser_cookie_stops_working_after_sign_out(self, engine) -> None:  # type: ignore[no-untyped-def]
        with TestClient(app) as browser:
            browser.headers.update(HEADERS)
            login = browser.post("/api/v1/auth/login", json={"email": NB_OFFICER, "password": DEMO_PASSWORD})
            assert login.status_code == 200
            token = browser.cookies.get(get_settings().session_cookie_name)
            assert browser.post("/api/v1/auth/logout").status_code == 204
        with TestClient(app) as thief:
            thief.cookies.set(get_settings().session_cookie_name, token, path="/api")
            assert thief.get("/api/v1/auth/me").status_code == 401

    def test_other_sessions_survive_one_device_signing_out(self, client: TestClient) -> None:
        first, second = _bearer(client, NB_OFFICER), _bearer(client, NB_OFFICER)
        client.post("/api/v1/auth/logout", headers=first)
        assert client.get("/api/v1/auth/me", headers=second).status_code == 200

    def _forged(self, user: User, **claims: object) -> dict[str, str]:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user.id),
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "jti": uuid.uuid4().hex,
            "typ": "access",
            "iss": "edushield-ai",
            **claims,
        }
        key = claims.pop("key", get_settings().jwt_secret.get_secret_value())  # type: ignore[arg-type]
        payload.pop("key", None)
        return {"Authorization": f"Bearer {jwt.encode(payload, key, algorithm='HS256')}"}

    def test_expired_tampered_and_incomplete_tokens_are_refused(self, client: TestClient, real_user: User) -> None:
        expired = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
        assert client.get("/api/v1/auth/me", headers=self._forged(real_user)).status_code == 200
        assert client.get("/api/v1/auth/me", headers=self._forged(real_user, exp=expired)).status_code == 401
        wrong_key = "another-key-that-is-long-enough-for-hmac-signing"
        assert client.get("/api/v1/auth/me", headers=self._forged(real_user, key=wrong_key)).status_code == 401
        assert client.get("/api/v1/auth/me", headers=self._forged(real_user, typ="refresh")).status_code == 401

    def test_deactivation_ends_access_immediately(self, client: TestClient, db: Session, real_user: User) -> None:
        headers = _bearer(client, REAL_EMAIL, PASSWORD)
        real_user.is_active = False
        db.commit()
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    def test_purge_removes_only_what_can_no_longer_be_used(self, db: Session, real_user: User) -> None:
        now = utcnow()
        db.add_all(
            [
                RevokedSession(jti="a" * 32, expires_at=now - timedelta(minutes=1)),
                RevokedSession(jti="b" * 32, expires_at=now + timedelta(minutes=30)),
                PasswordResetToken(user_id=real_user.id, token_hash="c" * 64, expires_at=now - timedelta(minutes=1)),
            ]
        )
        db.commit()
        assert purge_expired_credentials() == (1, 1)
        db.expire_all()
        assert db.get(RevokedSession, "b" * 32) is not None


class TestPasswordRecovery:
    def _request(self, client: TestClient, email: str):  # type: ignore[no-untyped-def]
        return client.post("/api/v1/auth/password-reset/request", json={"email": email})

    def test_response_never_reveals_whether_an_account_exists(
        self, client: TestClient, real_user: User, sent_links: list
    ) -> None:
        known, unknown = self._request(client, REAL_EMAIL), self._request(client, "nobody@northbridge.example")
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert [recipient for recipient, _ in sent_links] == [REAL_EMAIL]

    def test_demo_and_deactivated_accounts_get_no_link(
        self, client: TestClient, db: Session, real_user: User, sent_links: list
    ) -> None:
        real_user.is_active = False
        db.commit()
        assert self._request(client, REAL_EMAIL).status_code == 202
        assert self._request(client, NB_OFFICER).status_code == 202
        assert sent_links == []

    def test_reset_changes_the_password_once_and_ends_old_sessions(
        self, client: TestClient, db: Session, real_user: User, sent_links: list
    ) -> None:
        old_session = _bearer(client, REAL_EMAIL, PASSWORD)
        self._request(client, REAL_EMAIL)
        token = _token_from(sent_links[0][1])
        stored = db.scalar(select(PasswordResetToken))
        assert stored is not None and stored.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in stored.token_hash

        real_user.password_changed_at = utcnow() - timedelta(seconds=5)
        db.commit()
        confirm = {"token": token, "password": NEW_PASSWORD}
        assert client.post("/api/v1/auth/password-reset/confirm", json=confirm).status_code == 204
        assert client.post("/api/v1/auth/password-reset/confirm", json=confirm).status_code == 401
        assert client.post("/api/v1/auth/token", data={"username": REAL_EMAIL, "password": PASSWORD}).status_code == 401
        new_session = _bearer(client, REAL_EMAIL, NEW_PASSWORD)
        assert client.get("/api/v1/auth/me", headers=new_session).status_code == 200
        del old_session

    def test_expired_invalid_and_weak_resets_are_refused(
        self, client: TestClient, db: Session, real_user: User, sent_links: list
    ) -> None:
        self._request(client, REAL_EMAIL)
        token = _token_from(sent_links[0][1])
        url = "/api/v1/auth/password-reset/confirm"
        assert client.post(url, json={"token": token, "password": "weakweakweakweak"}).status_code == 422
        assert client.post(url, json={"token": "x" * 43, "password": NEW_PASSWORD}).status_code == 401
        stored = db.scalar(select(PasswordResetToken))
        assert stored is not None
        stored.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert client.post(url, json={"token": token, "password": NEW_PASSWORD}).status_code == 401

    def test_a_new_request_cancels_the_previous_link(
        self, client: TestClient, db: Session, real_user: User, sent_links: list
    ) -> None:
        self._request(client, REAL_EMAIL)
        first = _token_from(sent_links[0][1])
        stored = db.scalar(select(PasswordResetToken))
        assert stored is not None
        stored.created_at = utcnow() - timedelta(minutes=2)
        db.commit()
        self._request(client, REAL_EMAIL)
        assert len(sent_links) == 2
        url = "/api/v1/auth/password-reset/confirm"
        assert client.post(url, json={"token": first, "password": NEW_PASSWORD}).status_code == 401

    def test_repeat_requests_do_not_flood_the_mailbox(
        self, client: TestClient, real_user: User, sent_links: list
    ) -> None:
        for _ in range(4):
            assert self._request(client, REAL_EMAIL).status_code == 202
        assert len(sent_links) == 1

    def test_reset_is_rate_limited(self, client: TestClient) -> None:
        statuses = [self._request(client, "nobody@northbridge.example").status_code for _ in range(12)]
        assert statuses[:10] == [202] * 10 and statuses[-1] == 429


class TestAbuseLimits:
    def test_login_is_rate_limited_per_client(self, client: TestClient) -> None:
        body = {"email": "nobody@northbridge.example", "password": "wrong-password"}
        statuses = [client.post("/api/v1/auth/login", json=body).status_code for _ in range(22)]
        assert statuses[:20] == [401] * 20 and statuses[-1] == 429

    def test_activation_is_rate_limited(self, client: TestClient) -> None:
        body = {"token": "x" * 43, "password": PASSWORD}
        statuses = [client.post("/api/v1/student-activation", json=body).status_code for _ in range(12)]
        assert statuses[:10] == [401] * 10 and statuses[-1] == 401


class FakeRedis:
    """The two Redis operations the limiter uses, shared between limiter instances like a real store."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.down = False

    def pipeline(self) -> FakeRedis:
        self.pending: list[str] = []
        return self

    def incr(self, key: str) -> None:
        self.pending.append(key)

    def expire(self, key: str, seconds: int) -> None:
        del key, seconds

    def execute(self) -> list[object]:
        import redis

        if self.down:
            raise redis.ConnectionError("store down")
        key = self.pending[0]
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], True]


class TestSharedLimiter:
    def test_limit_holds_across_instances(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = FakeRedis()
        monkeypatch.setattr(ratelimit, "shared_store", lambda: store)
        instance_a, instance_b = RateLimiter("t", 3, 60), RateLimiter("t", 3, 60)
        assert [instance_a.allow("ip"), instance_b.allow("ip"), instance_a.allow("ip")] == [True, True, True]
        assert instance_b.allow("ip") is False
        assert instance_a.allow("another-ip") is True
        assert not any("ip" in key.split(":")[3] for key in store.counts)

    def test_store_outage_falls_back_to_a_local_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = FakeRedis()
        store.down = True
        monkeypatch.setattr(ratelimit, "shared_store", lambda: store)
        limiter = RateLimiter("t", 2, 60)
        assert [limiter.allow("ip"), limiter.allow("ip"), limiter.allow("ip")] == [True, True, False]


@pytest.mark.seeded
class TestBoundaries:
    def test_students_cannot_reach_staff_endpoints(self, as_user) -> None:  # type: ignore[no-untyped-def]
        student = as_user(DEMO_STUDENT_EMAIL)
        for path in (
            "applications",
            "dashboard/overview",
            "dashboard/applications",
            "alerts",
            "cases",
            "users",
            "audit/events",
        ):
            assert student.get(f"/api/v1/{path}").status_code == 403, path

    def test_staff_cannot_select_another_institution(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        other = db.scalar(select(Organization).where(Organization.slug == "lakeshore"))
        assert other is not None
        officer = as_user(NB_OFFICER)
        scoped = officer.get("/api/v1/applications", headers={"X-Organization-Id": str(other.id)})
        assert scoped.status_code == 200
        assert {row["organization"]["slug"] for row in scoped.json()["items"]} == {"northbridge"}

    def test_read_only_users_cannot_make_decisions(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        record = db.scalar(select(FinancialAidApplication).where(FinancialAidApplication.submitted_at.is_not(None)))
        assert record is not None
        auditor = as_user(NB_AUDITOR)
        body = {"review_status": "cleared", "note": "Attempted by an auditor."}
        assert auditor.patch(f"/api/v1/applications/{record.id}/review", json=body).status_code == 403
        assert auditor.post(f"/api/v1/applications/{record.id}/assess").status_code == 403

    def test_a_revoked_invitation_cannot_be_activated(self, as_user, db: Session, client: TestClient) -> None:  # type: ignore[no-untyped-def]
        from app.models import Student

        admin = as_user(NB_ADMIN)
        student = db.scalar(
            select(Student)
            .where(
                Student.organization_id == db.scalar(select(Organization.id).where(Organization.slug == "northbridge"))
            )
            .order_by(Student.student_ref.desc())
        )
        assert student is not None
        invitation = admin.post(
            f"/api/v1/students/{student.id}/invitation", json={"email": "revoked@northbridge.example"}
        )
        assert invitation.status_code == 201, invitation.text
        token = invitation.json()["activation_url"].split("token=")[1]
        assert admin.post(f"/api/v1/student-invitations/{invitation.json()['id']}/revoke").status_code == 200
        assert client.post("/api/v1/student-activation", json={"token": token, "password": PASSWORD}).status_code == 401

    def test_another_institutions_staff_cannot_revoke_an_invitation(self, as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
        from app.models import Student

        student = db.scalar(
            select(Student)
            .where(
                Student.organization_id == db.scalar(select(Organization.id).where(Organization.slug == "northbridge"))
            )
            .order_by(Student.student_ref.desc())
        )
        assert student is not None
        invitation = as_user(NB_ADMIN).post(
            f"/api/v1/students/{student.id}/invitation", json={"email": "scoped@northbridge.example"}
        )
        assert invitation.status_code == 201, invitation.text
        lakeshore = as_user(LS_INVESTIGATOR)
        assert lakeshore.post(f"/api/v1/student-invitations/{invitation.json()['id']}/revoke").status_code == 403


class TestClientAddress:
    def _request(self, headers: dict[str, str], peer: str = "10.0.0.9"):  # type: ignore[no-untyped-def]
        from starlette.requests import Request

        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
        }
        return Request(scope)

    def _with_header(self, monkeypatch: pytest.MonkeyPatch, header: str | None) -> None:
        from app.core import client

        settings = get_settings().model_copy(update={"client_ip_header": header})
        monkeypatch.setattr(client, "get_settings", lambda: settings)

    def test_forwarded_headers_are_ignored_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.client import client_address

        self._with_header(monkeypatch, None)
        request = self._request({"X-Forwarded-For": "203.0.113.5", "X-Real-IP": "203.0.113.6"})
        assert client_address(request) == "10.0.0.9"

    def test_only_the_configured_header_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.client import client_address

        self._with_header(monkeypatch, "X-Real-IP")
        request = self._request({"X-Forwarded-For": "203.0.113.5", "X-Real-IP": "198.51.100.7"})
        assert client_address(request) == "198.51.100.7"

    @pytest.mark.parametrize("value", ["", "not-an-address", "1.2.3.4.5"])
    def test_unusable_values_fall_back_to_the_connection(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        from app.core.client import client_address

        self._with_header(monkeypatch, "X-Real-IP")
        assert client_address(self._request({"X-Real-IP": value})) == "10.0.0.9"

    def test_rotating_a_forged_header_cannot_escape_the_login_limit(self, client: TestClient) -> None:
        body = {"email": "nobody@northbridge.example", "password": "wrong-password"}
        codes = [
            client.post("/api/v1/auth/login", json=body, headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
            for i in range(22)
        ]
        assert codes[-1] == 429
