"""Decides who hears about an application status change. Each history row produces each message once."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApplicationStatusHistory, FinancialAidApplication, User
from app.models.enums import ApplicationStatus as S
from app.services.email_outbox import enqueue

_STUDENT_TEMPLATES = {
    S.SUBMITTED.value: "application_submitted",
    S.ADDITIONAL_INFORMATION_REQUIRED.value: "additional_information_requested",
    S.APPROVED.value: "application_decided",
    S.REJECTED.value: "application_decided",
}


def queue_status_emails(
    db: Session, app: FinancialAidApplication, history: ApplicationStatusHistory | None
) -> list[uuid.UUID]:
    """Call before committing the status change, so the event and its messages succeed or fail together."""
    if history is None:
        return []
    context = {"reference": app.reference}
    queued: list[uuid.UUID | None] = []
    template = _STUDENT_TEMPLATES.get(history.to_status)
    student_user = db.scalar(select(User).where(User.student_id == app.student_id))
    if template and student_user is not None:
        queued.append(
            enqueue(
                db,
                user=student_user,
                organization_id=app.organization_id,
                template=template,
                context=context,
                dedupe_key=f"{template}:{history.id}",
            )
        )
    if history.to_status == S.SUBMITTED.value and history.from_status == S.ADDITIONAL_INFORMATION_REQUIRED.value:
        request = db.scalar(
            select(ApplicationStatusHistory)
            .where(
                ApplicationStatusHistory.application_id == app.id,
                ApplicationStatusHistory.to_status == S.ADDITIONAL_INFORMATION_REQUIRED.value,
            )
            .order_by(ApplicationStatusHistory.created_at.desc())
            .limit(1)
        )
        requester = db.get(User, request.actor_user_id) if request and request.actor_user_id else None
        if requester is not None:
            queued.append(
                enqueue(
                    db,
                    user=requester,
                    organization_id=app.organization_id,
                    template="application_response_received",
                    context=context,
                    dedupe_key=f"application_response_received:{history.id}",
                )
            )
    return [item for item in queued if item is not None]
