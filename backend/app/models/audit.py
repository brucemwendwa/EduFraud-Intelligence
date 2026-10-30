"""Tamper-evident audit trail.

Each event stores the SHA-256 hash of its own canonical content plus the previous
event's hash, forming a chain: altering or removing any row breaks verification of
every later row. Database triggers (see the initial migration) reject UPDATE and
DELETE on this table, and the API exposes no mutation endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey
from app.db.types import utcnow


class AuditEvent(UUIDPrimaryKey, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_org_time", "organization_id", "occurred_at"),
        Index("ix_audit_target", "target_type", "target_id"),
    )

    sequence: Mapped[int] = mapped_column(BigInteger, unique=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(default=utcnow)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(254))
    actor_role: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(24), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(12))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    target_ref: Mapped[str | None] = mapped_column(String(48))
    ip_hash: Mapped[str | None] = mapped_column(String(16))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
