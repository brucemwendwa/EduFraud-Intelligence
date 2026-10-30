from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import app
from app.models.enums import AuditCategory
from app.services import audit
from tests.conftest import ADMIN, NB_AUDITOR


def test_chain_verifies_after_normal_activity(as_user) -> None:  # type: ignore[no-untyped-def]
    auditor = as_user(NB_AUDITOR)
    as_user(ADMIN)
    result = auditor.get("/api/v1/audit/verify").json()
    assert result["valid"] is True and result["events_checked"] >= 2


def test_tampering_is_detected(db: Session) -> None:
    for i in range(3):
        audit.record(db, category=AuditCategory.SYSTEM, action=f"test.event.{i}")
        db.commit()
    assert audit.verify_chain(db).valid

    # Simulate an attacker with raw database access: bypass the trigger and rewrite history.
    db.execute(text("DROP TRIGGER trg_audit_events_no_update"))
    db.execute(text("UPDATE audit_events SET action = 'nothing.to.see' WHERE sequence = 2"))
    db.commit()
    result = audit.verify_chain(db)
    assert result.valid is False
    assert result.first_broken_sequence == 2


def test_events_in_one_transaction_extend_the_chain_in_order(db: Session) -> None:
    first = audit.record(db, category=AuditCategory.SYSTEM, action="batch.one")
    second = audit.record(db, category=AuditCategory.SYSTEM, action="batch.two")
    db.commit()
    assert second.sequence == first.sequence + 1 and second.prev_hash == first.hash
    assert audit.verify_chain(db).valid


def test_audit_api_exposes_no_mutation_routes() -> None:
    methods = {
        method for path, ops in app.openapi()["paths"].items() if path.startswith("/api/v1/audit") for method in ops
    }
    assert methods == {"get"}
