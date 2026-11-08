"""Removes credentials that can no longer be used."""

from __future__ import annotations

from sqlalchemy import delete

from app.db.session import SessionLocal
from app.db.types import utcnow
from app.models import PasswordResetToken, RevokedSession


def purge_expired_credentials() -> tuple[int, int]:
    with SessionLocal() as db:
        now = utcnow()
        sessions = db.execute(delete(RevokedSession).where(RevokedSession.expires_at <= now)).rowcount
        tokens = db.execute(delete(PasswordResetToken).where(PasswordResetToken.expires_at <= now)).rowcount
        db.commit()
    return sessions, tokens
