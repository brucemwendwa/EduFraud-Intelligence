"""Guarded financial-aid application state transitions."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models import ApplicationStatusHistory, FinancialAidApplication, User
from app.models.enums import ApplicationStatus, AuditCategory
from app.services import audit

STUDENT_EDITABLE = {ApplicationStatus.DRAFT, ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED}
STUDENT_SUBMITTABLE = STUDENT_EDITABLE
STUDENT_WITHDRAWABLE = {
    ApplicationStatus.DRAFT,
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.IN_REVIEW,
    ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED,
}
STAFF_TARGETS = {
    ApplicationStatus.IN_REVIEW,
    ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED,
    ApplicationStatus.APPROVED,
    ApplicationStatus.REJECTED,
    ApplicationStatus.ON_HOLD,  # compatibility with established staff review records
}

_STAFF_TRANSITIONS = {
    ApplicationStatus.SUBMITTED: STAFF_TARGETS,
    ApplicationStatus.RECEIVED: STAFF_TARGETS,
    ApplicationStatus.IN_REVIEW: STAFF_TARGETS,
    ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED: {
        ApplicationStatus.IN_REVIEW,
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
    },
    ApplicationStatus.ON_HOLD: STAFF_TARGETS,
}


def change_status(
    db: Session,
    app: FinancialAidApplication,
    *,
    to_status: ApplicationStatus,
    actor: User,
    request: Request | None,
    action: str,
    note: str | None = None,
) -> None:
    """Record a deliberate lifecycle movement and its audit event in one transaction."""
    before = app.status
    if before == to_status.value:
        return
    app.status = to_status.value
    db.add(
        ApplicationStatusHistory(
            organization_id=app.organization_id,
            application_id=app.id,
            from_status=before,
            to_status=to_status.value,
            actor_user_id=actor.id,
            actor_role=actor.role.key,
            note=note,
        )
    )
    audit.record(
        db,
        category=AuditCategory.APPLICATION,
        action=action,
        actor=actor,
        organization_id=app.organization_id,
        target_type="application",
        target_id=app.id,
        target_ref=app.reference,
        details={"from_status": before, "to_status": to_status.value},
        request=request,
    )


def require_transition(current: str, allowed: set[ApplicationStatus], target: ApplicationStatus) -> None:
    if ApplicationStatus(current) not in allowed:
        raise ConflictError(f"This application cannot be changed to {target.value} in its current state.")


def require_staff_transition(current: str, target: ApplicationStatus) -> None:
    if target not in _STAFF_TRANSITIONS.get(ApplicationStatus(current), set()):
        raise ConflictError("This staff decision is not valid for the application's current state.")
