from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import Schema


class AuditEventOut(Schema):
    id: uuid.UUID
    sequence: int
    organization_id: uuid.UUID | None
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    category: str
    action: str
    outcome: str
    target_type: str | None
    target_id: str | None
    target_ref: str | None
    details: dict[str, Any]
    hash: str
    prev_hash: str


class ChainVerificationOut(Schema):
    valid: bool
    events_checked: int
    first_broken_sequence: int | None
    verified_at: datetime


class AuditSummary(Schema):
    total_events: int
    by_category: dict[str, int]
    denied_last_7_days: int
    failed_logins_last_7_days: int
