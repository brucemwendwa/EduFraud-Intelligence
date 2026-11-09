"""Writes notifications in the same transaction as their event, and delivers them afterwards.

Delivery failure never reaches the request that caused it. The portal remains the record of
truth, so a student sees every status change whether or not the email arrives.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.types import utcnow
from app.models import EmailOutbox, User
from app.services.email_templates import OUTBOX_TEMPLATES
from app.services.mailer import get_mailer

logger = logging.getLogger("edushield.mail")
MAX_ATTEMPTS = 5
_BASE_RETRY_SECONDS = 60


def enqueue(
    db: Session,
    *,
    user: User,
    organization_id: uuid.UUID,
    template: str,
    context: dict[str, Any],
    dedupe_key: str,
) -> uuid.UUID | None:
    """Adds a message unless this event already produced one. The caller commits."""
    if db.scalar(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == dedupe_key)) is not None:
        return None
    item = EmailOutbox(
        organization_id=organization_id,
        recipient_user_id=user.id,
        template=template,
        context=context,
        dedupe_key=dedupe_key,
        status="queued",
        attempts=0,
    )
    db.add(item)
    return item.id


def deliver(outbox_id: uuid.UUID) -> str | None:
    """Sends one message. The row lock makes duplicate dispatch harmless."""
    settings = get_settings()
    with SessionLocal() as db:
        item = db.scalar(select(EmailOutbox).where(EmailOutbox.id == outbox_id).with_for_update())
        if item is None or item.status not in ("queued", "retry"):
            return None
        if item.next_attempt_at and item.next_attempt_at > utcnow():
            return None
        user = db.get(User, item.recipient_user_id)
        if user is None or not user.is_active:
            item.status = "cancelled"
            db.commit()
            return item.status
        if settings.email_provider != "smtp":
            item.status = "suppressed"  # never reported as delivered
            db.commit()
            return item.status
        item.attempts += 1
        try:
            content = OUTBOX_TEMPLATES[item.template](item.context, settings.public_app_url)
            get_mailer(settings).send(recipient=user.email, content=content)
        except Exception as exc:  # noqa: BLE001 - only the error class is kept: messages can contain addresses
            item.error_code = type(exc).__name__[:40]
            logger.warning("email_delivery_failed", extra={"outbox_id": str(item.id), "error": item.error_code})
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "failed"
            else:
                item.status = "retry"
                item.next_attempt_at = utcnow() + timedelta(seconds=_BASE_RETRY_SECONDS * 2 ** (item.attempts - 1))
        else:
            item.status, item.sent_at, item.error_code = "sent", utcnow(), None
        db.commit()
        return item.status


def due_messages() -> list[uuid.UUID]:
    """Messages whose dispatch was lost or that are ready to retry. Safe to call repeatedly."""
    with SessionLocal() as db:
        now = utcnow()
        return list(
            db.scalars(
                select(EmailOutbox.id).where(
                    EmailOutbox.status.in_(("queued", "retry")),
                    (EmailOutbox.next_attempt_at.is_(None)) | (EmailOutbox.next_attempt_at <= now),
                )
            )
        )
