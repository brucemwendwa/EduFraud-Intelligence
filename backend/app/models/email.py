from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey


class EmailOutbox(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    """A notification owed to a user. Written with the event it reports, then delivered separately.

    Holds a user reference rather than an address, and never holds a secret: emails that carry an
    activation or reset link are sent directly and are not stored here.
    """

    __tablename__ = "email_outbox"
    __table_args__ = (Index("ix_email_outbox_status_retry", "status", "next_attempt_at"),)

    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template: Mapped[str] = mapped_column(String(40))
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    # One message per event: a repeated event finds its key already present and sends nothing.
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None]
    sent_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(40))
