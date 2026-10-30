"""In-app notifications for the people who need to act."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import P
from app.models import Notification, User


def notify_permission_holders(
    db: Session,
    *,
    organization_id: uuid.UUID,
    permission: P,
    kind: str,
    title: str,
    body: str,
    link: str | None = None,
    exclude: uuid.UUID | None = None,
) -> int:
    users = db.scalars(select(User).where(User.organization_id == organization_id, User.is_active)).all()
    count = 0
    for user in users:
        if user.id != exclude and permission.value in user.permission_keys:
            db.add(
                Notification(
                    user_id=user.id, organization_id=organization_id, kind=kind, title=title, body=body, link=link
                )
            )
            count += 1
    return count


def notify_user(
    db: Session, *, user_id: uuid.UUID, organization_id: uuid.UUID | None, kind: str, title: str, body: str, link: str
) -> None:
    db.add(Notification(user_id=user_id, organization_id=organization_id, kind=kind, title=title, body=body, link=link))
