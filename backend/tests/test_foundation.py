"""Phase 3 foundation: migrations, audit immutability, security primitives, logging, HTTP hardening."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.logging import REDACTED, JsonFormatter, RedactingFilter
from app.core.tokenization import TokenType, display_token, tokenize
from app.models import AuditEvent, Organization, Student
from tests.conftest import run_migrations


class TestMigrations:
    def test_upgrade_head_creates_every_table(self, tmp_path: Path) -> None:
        url = f"sqlite:///{tmp_path / 'fresh.db'}"
        run_migrations(url)
        from sqlalchemy import create_engine

        tables = set(inspect(create_engine(url)).get_table_names())
        expected = {
            "organizations",
            "users",
            "roles",
            "permissions",
            "role_permissions",
            "students",
            "student_identity_tokens",
            "financial_aid_applications",
            "enrollment_records",
            "payment_destination_tokens",
            "disbursements",
            "identity_verifications",
            "risk_assessments",
            "fraud_signals",
            "alerts",
            "investigation_cases",
            "case_evidence",
            "case_notes",
            "audit_events",
            "detection_runs",
            "notifications",
        }
        assert expected <= tables


def _org(db: Session) -> Organization:
    org = Organization(
        name="Test University",
        slug="test-u",
        institution_type="public_4yr",
        city="Columbus",
        state="OH",
        synthetic_ope_id="SYN-T0001",
    )
    db.add(org)
    db.flush()
    return org


def _audit_row(seq: int) -> AuditEvent:
    return AuditEvent(
        sequence=seq,
        category="system",
        action="test.event",
        outcome="success",
        prev_hash="0" * 64,
        hash=uuid.uuid4().hex + uuid.uuid4().hex,
    )


class TestAuditImmutability:
    def test_database_rejects_update(self, db: Session) -> None:
        db.add(_audit_row(1))
        db.commit()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("UPDATE audit_events SET action = 'tampered'"))
        db.rollback()

    def test_database_rejects_delete(self, db: Session) -> None:
        db.add(_audit_row(1))
        db.commit()
        with pytest.raises(DatabaseError, match="append-only"):
            db.execute(text("DELETE FROM audit_events"))
        db.rollback()
        assert db.query(AuditEvent).count() == 1


class TestPrivacyPrimitives:
    def test_tokenization_is_deterministic_and_normalized(self) -> None:
        assert tokenize(TokenType.SSN, "000-12-3456") == tokenize(TokenType.SSN, "000123456")
        assert tokenize(TokenType.EMAIL, " Ana@Example.EDU ") == tokenize(TokenType.EMAIL, "ana@example.edu")

    def test_tokens_are_type_scoped_and_irreversible_looking(self) -> None:
        ssn = tokenize(TokenType.SSN, "000123456")
        assert ssn != tokenize(TokenType.PHONE, "000123456")
        assert len(ssn) == 64 and "000123456" not in ssn
        assert display_token(ssn).startswith("TKN-")

    def test_names_are_encrypted_at_rest(self, db: Session) -> None:
        org = _org(db)
        db.add(
            Student(
                organization_id=org.id,
                student_ref="STU-1",
                first_name="Avery",
                last_name="Lindqvist",
                birth_year=2004,
                state_of_residence="OH",
            )
        )
        db.commit()
        raw = db.execute(text("SELECT first_name, last_name FROM students")).one()
        assert "Avery" not in raw[0] and "Lindqvist" not in raw[1]
        assert db.query(Student).one().first_name == "Avery"
        assert crypto.decrypt(crypto.encrypt("x")) == "x"

    def test_datetimes_round_trip_as_utc(self, db: Session) -> None:
        org = _org(db)
        db.commit()
        db.expire_all()
        assert db.get(Organization, org.id).created_at.tzinfo is not None  # type: ignore[union-attr]


class TestLogRedaction:
    def _format(self, msg: str, *args: object, **extra: object) -> dict:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, msg, args, None)
        record.__dict__.update(extra)
        RedactingFilter().filter(record)
        return json.loads(JsonFormatter().format(record))

    def test_scrubs_sensitive_patterns_from_messages(self) -> None:
        out = self._format("ssn=%s auth=%s", "123-45-6789", "Bearer eyJhbGciOi.eyJzdWIiOiIx.sig")
        assert "123-45-6789" not in out["msg"] and "eyJhbGciOi" not in out["msg"]
        assert out["msg"].count(REDACTED) == 2

    def test_masks_sensitive_structured_fields(self) -> None:
        out = self._format("login", password="hunter2", account_number="12345678", path="/api/v1/auth/login")
        assert out["password"] == REDACTED
        assert out["account_number"] == REDACTED
        assert out["path"] == "/api/v1/auth/login"


class TestHttpHardening:
    def test_health_and_security_headers(self, client) -> None:  # type: ignore[no-untyped-def]
        res = client.get("/api/health")
        assert res.status_code == 200 and res.json()["status"] == "ok"
        assert res.headers["x-content-type-options"] == "nosniff"
        assert res.headers["x-frame-options"] == "DENY"
        assert "x-request-id" in res.headers

    def test_readiness_checks_database(self, client) -> None:  # type: ignore[no-untyped-def]
        assert client.get("/api/ready").json()["database"] == "ok"

    def test_cookie_authenticated_writes_require_client_header(self, client) -> None:  # type: ignore[no-untyped-def]
        client.cookies.set("edushield_session", "anything")
        res = client.post("/api/v1/cases", json={})
        assert res.status_code == 403
        assert res.json()["error"]["code"] == "csrf_check_failed"

    def test_unknown_route_uses_error_envelope(self, client) -> None:  # type: ignore[no-untyped-def]
        res = client.get("/api/v1/does-not-exist")
        assert res.status_code == 404 and res.json()["error"]["code"] == "http_404"


def test_now_is_timezone_aware() -> None:
    assert datetime.now(UTC).tzinfo is UTC
