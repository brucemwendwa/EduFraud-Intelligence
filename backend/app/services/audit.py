"""Append-only, hash-chained audit trail.

`record()` adds an event to the caller's session without committing, so the audit
entry commits atomically with the business change it describes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging import redact_value
from app.core.tokenization import hash_ip
from app.db.types import utcnow
from app.models import AuditEvent, User
from app.models.enums import AuditCategory, AuditOutcome

GENESIS_HASH = "0" * 64
_PG_AUDIT_LOCK = 727_001


def _canonical(event: AuditEvent) -> bytes:
    payload = {
        "sequence": event.sequence,
        "organization_id": str(event.organization_id) if event.organization_id else None,
        "occurred_at": event.occurred_at.isoformat(),
        "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
        "actor_email": event.actor_email,
        "category": event.category,
        "action": event.action,
        "outcome": event.outcome,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "target_ref": event.target_ref,
        "details": event.details,
        "prev_hash": event.prev_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def compute_hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()


def record(
    db: Session,
    *,
    category: AuditCategory,
    action: str,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    actor: User | None = None,
    organization_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    target_ref: str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    actor_email: str | None = None,
) -> AuditEvent:
    if db.get_bind().dialect.name == "postgresql":
        # Serialize chain extension across concurrent transactions.
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PG_AUDIT_LOCK})
    last = db.execute(
        select(AuditEvent.sequence, AuditEvent.hash).order_by(AuditEvent.sequence.desc()).limit(1)
    ).first()
    pending = [o for o in db.new if isinstance(o, AuditEvent)]
    if pending:  # events added earlier in this same unit of work extend the chain first
        tail = max(pending, key=lambda e: e.sequence)
        last = (tail.sequence, tail.hash)

    event = AuditEvent(
        id=uuid.uuid4(),
        sequence=(last[0] + 1) if last else 1,
        organization_id=organization_id if organization_id else (actor.organization_id if actor else None),
        occurred_at=utcnow(),
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else actor_email,
        actor_role=actor.role.key if actor else None,
        category=category.value,
        action=action,
        outcome=outcome.value,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        target_ref=target_ref,
        ip_hash=hash_ip(request.client.host) if request and request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:200] if request else None,
        details=json.loads(json.dumps(redact_value("details", details or {}), default=str)),
        prev_hash=last[1] if last else GENESIS_HASH,
    )
    event.hash = compute_hash(event)
    db.add(event)
    return event


@dataclass
class ChainVerification:
    valid: bool
    events_checked: int
    first_broken_sequence: int | None
    verified_at: datetime


def verify_chain(db: Session) -> ChainVerification:
    """Recomputes every hash in sequence order. Any edit, insertion or removal is detected."""
    prev = GENESIS_HASH
    count = 0
    expected_seq = 1
    for event in db.scalars(select(AuditEvent).order_by(AuditEvent.sequence)).yield_per(500):
        count += 1
        if event.sequence != expected_seq or event.prev_hash != prev or compute_hash(event) != event.hash:
            return ChainVerification(False, count, event.sequence, utcnow())
        prev = event.hash
        expected_seq += 1
    return ChainVerification(True, count, None, utcnow())
