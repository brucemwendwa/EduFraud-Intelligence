"""Student-owned financial-aid application lifecycle endpoints."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import DB, Principal, require
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.detection.engine import DetectionEngine
from app.models import ApplicationStatusHistory, FinancialAidApplication, Student
from app.models.enums import ApplicationStatus, AuditCategory, AuditOutcome, ReviewStatus, VerificationStatus
from app.schemas.student_applications import (
    StudentApplicationDraft,
    StudentApplicationHistory,
    StudentApplicationOut,
    StudentApplicationSubmit,
    StudentStatusMessage,
)
from app.services import audit
from app.services.application_lifecycle import (
    STUDENT_EDITABLE,
    STUDENT_SUBMITTABLE,
    STUDENT_WITHDRAWABLE,
    change_status,
    require_transition,
)

router = APIRouter(prefix="/student-applications", tags=["student applications"])
logger = logging.getLogger("edushield.applications")

# Statuses where the financial aid office's explanation is shown prominently to the student.
_EXPLAINED_STATUSES = {
    ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED,
    ApplicationStatus.APPROVED,
    ApplicationStatus.REJECTED,
}


def _student(db: DB, principal: Principal) -> Student:
    if principal.user.student_id is None:
        raise ForbiddenError("This account is not linked to a student record.")
    student = db.get(Student, principal.user.student_id)
    if student is None or student.organization_id != principal.user.organization_id:
        raise ForbiddenError("This student record is unavailable.")
    return student


def _owned_application(db: DB, application_id: uuid.UUID, principal: Principal) -> FinancialAidApplication:
    student = _student(db, principal)
    app = db.get(FinancialAidApplication, application_id)
    if app is None or app.student_id != student.id or app.organization_id != student.organization_id:
        raise NotFoundError("Application not found.")
    return app


def _field_requirements(app: FinancialAidApplication) -> list[str]:
    missing = []
    for field, label in (
        (app.award_year, "award year"),
        (app.dependency_status, "dependency status"),
        (app.enrollment_intensity, "enrollment intensity"),
        (app.program, "program"),
        (app.requested_amount if app.requested_amount and app.requested_amount > 0 else None, "requested amount"),
        (app.student_aid_index, "student aid index"),
    ):
        if field is None or (isinstance(field, str) and not field.strip()):
            missing.append(label)
    return missing


def _requirements(app: FinancialAidApplication) -> list[str]:
    missing = _field_requirements(app)
    if app.status == ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED:
        missing.insert(0, "additional information requested by your financial aid office")
    return missing


def _history_rows(db: DB, app: FinancialAidApplication) -> list[ApplicationStatusHistory]:
    """Status changes only: staff review notes recorded without a status change never reach the student."""
    rows = db.scalars(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == app.id)
        .order_by(ApplicationStatusHistory.created_at)
    ).all()
    return [row for row in rows if row.from_status != row.to_status]


def _history_out(row: ApplicationStatusHistory) -> StudentApplicationHistory:
    return StudentApplicationHistory(
        from_status=row.from_status,
        to_status=row.to_status,
        # The specific staff role (for example, fraud investigator) is internal.
        actor_role="student" if row.actor_role == "student" else "financial_aid_office",
        student_message=row.student_message,
        created_at=row.created_at,
    )


def _status_message(app: FinancialAidApplication, rows: list[ApplicationStatusHistory]) -> StudentStatusMessage | None:
    if ApplicationStatus(app.status) not in _EXPLAINED_STATUSES:
        return None
    latest = next((row for row in reversed(rows) if row.to_status == app.status), None)
    if latest is None:
        return None
    return StudentStatusMessage(status=app.status, message=latest.student_message, created_at=latest.created_at)


def _out(db: DB, app: FinancialAidApplication) -> StudentApplicationOut:
    rows = _history_rows(db, app)
    status = ApplicationStatus(app.status)
    return StudentApplicationOut(
        id=app.id,
        reference=app.reference,
        award_year=app.award_year,
        status=app.status,
        submitted_at=app.submitted_at,
        dependency_status=app.dependency_status,
        enrollment_intensity=app.enrollment_intensity,
        program=app.program,
        requested_amount=app.requested_amount,
        student_aid_index=app.student_aid_index,
        is_editable=status in STUDENT_EDITABLE,
        is_withdrawable=status in STUDENT_WITHDRAWABLE,
        outstanding_requirements=_requirements(app),
        status_message=_status_message(app, rows),
        history=[_history_out(row) for row in rows],
    )


def _reference(db: DB) -> str:
    for _ in range(5):
        ref = f"FA-{utcnow().year}-{secrets.token_hex(4).upper()}"
        if db.scalar(select(FinancialAidApplication.id).where(FinancialAidApplication.reference == ref)) is None:
            return ref
    raise ConflictError("Could not allocate an application reference. Please try again.")


@router.get("", response_model=list[StudentApplicationOut], summary="Signed-in student's applications")
def list_student_applications(
    db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]
) -> list[StudentApplicationOut]:
    student = _student(db, principal)
    apps = db.scalars(
        select(FinancialAidApplication)
        .where(FinancialAidApplication.student_id == student.id)
        .order_by(FinancialAidApplication.created_at.desc())
    ).all()
    return [_out(db, app) for app in apps]


@router.post(
    "", response_model=StudentApplicationOut, status_code=201, summary="Create a financial-aid application draft"
)
def create_student_application(
    body: StudentApplicationDraft,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
) -> StudentApplicationOut:
    student = _student(db, principal)
    app = FinancialAidApplication(
        organization_id=student.organization_id,
        student_id=student.id,
        reference=_reference(db),
        status=ApplicationStatus.DRAFT,
        submission_channel="student_portal",
        verification_status=VerificationStatus.NOT_REQUIRED,
        review_status=ReviewStatus.UNREVIEWED,
        **body.model_dump(exclude_none=True),
    )
    db.add(app)
    db.flush()
    db.add(
        ApplicationStatusHistory(
            organization_id=app.organization_id,
            application_id=app.id,
            from_status=None,
            to_status=ApplicationStatus.DRAFT,
            actor_user_id=principal.user.id,
            actor_role=principal.user.role.key,
            note=None,
        )
    )
    audit.record(
        db, category=AuditCategory.APPLICATION, action="application.draft_create", actor=principal.user,
        organization_id=app.organization_id, target_type="application", target_id=app.id, target_ref=app.reference,
        request=request,
    )
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.get("/{application_id}", response_model=StudentApplicationOut, summary="Signed-in student's application detail")
def get_student_application(
    application_id: uuid.UUID, db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]
) -> StudentApplicationOut:
    return _out(db, _owned_application(db, application_id, principal))


@router.patch("/{application_id}", response_model=StudentApplicationOut, summary="Save an editable application draft")
def update_student_application(
    application_id: uuid.UUID,
    body: StudentApplicationDraft,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
) -> StudentApplicationOut:
    app = _owned_application(db, application_id, principal)
    if ApplicationStatus(app.status) not in STUDENT_EDITABLE:
        raise ConflictError(
            "Submitted applications cannot be edited. Contact your financial aid office if information changes."
        )
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise ValidationFailedError("Choose at least one application field to update.")
    for field, value in values.items():
        setattr(app, field, value)
    audit.record(
        db, category=AuditCategory.APPLICATION, action="application.draft_update", actor=principal.user,
        organization_id=app.organization_id, target_type="application", target_id=app.id, target_ref=app.reference,
        details={"fields": sorted(values)}, request=request,
    )
    db.commit()
    db.refresh(app)
    return _out(db, app)


def _assess_after_submission(db: DB, app: FinancialAidApplication, principal: Principal, request: Request) -> None:
    """Score the submitted application. A scoring failure must never cost a student their submission."""
    try:
        DetectionEngine(db).prepare().assess(app, triggered_by="student_submission", user=principal.user)
        db.commit()
    except Exception:  # noqa: BLE001 - reviewers see the application as "not yet assessed" and can re-run it
        db.rollback()
        logger.exception("risk_assessment_failed", extra={"application_id": str(app.id)})
        audit.record(
            db, category=AuditCategory.DETECTION, action="application.assessment_failed", outcome=AuditOutcome.FAILURE,
            actor=principal.user, organization_id=app.organization_id, target_type="application", target_id=app.id,
            target_ref=app.reference, request=request,
        )
        db.commit()


@router.post("/{application_id}/submit", response_model=StudentApplicationOut, summary="Submit a completed application")
def submit_student_application(
    application_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
    body: StudentApplicationSubmit | None = None,
) -> StudentApplicationOut:
    app = _owned_application(db, application_id, principal)
    require_transition(app.status, STUDENT_SUBMITTABLE, ApplicationStatus.SUBMITTED)
    missing = _field_requirements(app)
    if missing:
        raise ValidationFailedError(
            "Complete the required information before submitting.", details=[{"field": x} for x in missing]
        )
    response_note = (body.response_note or "").strip() or None if body else None
    app.submitted_at = utcnow()
    change_status(
        db,
        app,
        to_status=ApplicationStatus.SUBMITTED,
        actor=principal.user,
        request=request,
        action="application.submit",
        note=response_note,
        student_message=response_note,
    )
    db.commit()
    _assess_after_submission(db, app, principal, request)
    db.refresh(app)
    return _out(db, app)


@router.post("/{application_id}/withdraw", response_model=StudentApplicationOut, summary="Withdraw an application")
def withdraw_student_application(
    application_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
) -> StudentApplicationOut:
    app = _owned_application(db, application_id, principal)
    require_transition(app.status, STUDENT_WITHDRAWABLE, ApplicationStatus.WITHDRAWN)
    change_status(
        db,
        app,
        to_status=ApplicationStatus.WITHDRAWN,
        actor=principal.user,
        request=request,
        action="application.withdraw",
    )
    db.commit()
    db.refresh(app)
    return _out(db, app)
