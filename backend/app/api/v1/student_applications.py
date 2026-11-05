"""Student-owned financial-aid application lifecycle endpoints."""

from __future__ import annotations

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
from app.models.enums import ApplicationStatus, AuditCategory, ReviewStatus, VerificationStatus
from app.schemas.student_applications import StudentApplicationDraft, StudentApplicationHistory, StudentApplicationOut
from app.services import audit
from app.services.application_lifecycle import (
    STUDENT_EDITABLE,
    STUDENT_SUBMITTABLE,
    STUDENT_WITHDRAWABLE,
    change_status,
    require_transition,
)

router = APIRouter(prefix="/student-applications", tags=["student applications"])


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


def _history(db: DB, app: FinancialAidApplication) -> list[StudentApplicationHistory]:
    rows = db.scalars(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == app.id)
        .order_by(ApplicationStatusHistory.created_at)
    ).all()
    return [StudentApplicationHistory.model_validate(row) for row in rows]


def _out(db: DB, app: FinancialAidApplication) -> StudentApplicationOut:
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
        risk_level=app.risk_level,
        is_editable=ApplicationStatus(app.status) in STUDENT_EDITABLE,
        outstanding_requirements=_requirements(app),
        history=_history(db, app),
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


@router.post("/{application_id}/submit", response_model=StudentApplicationOut, summary="Submit a completed application")
def submit_student_application(
    application_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
) -> StudentApplicationOut:
    app = _owned_application(db, application_id, principal)
    require_transition(app.status, STUDENT_SUBMITTABLE, ApplicationStatus.SUBMITTED)
    missing = _field_requirements(app)
    if missing:
        raise ValidationFailedError(
            "Complete the required information before submitting.", details=[{"field": x} for x in missing]
        )
    app.submitted_at = utcnow()
    change_status(
        db,
        app,
        to_status=ApplicationStatus.SUBMITTED,
        actor=principal.user,
        request=request,
        action="application.submit",
    )
    DetectionEngine(db).prepare().assess(app, triggered_by="student_submission", user=principal.user)
    db.commit()
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
