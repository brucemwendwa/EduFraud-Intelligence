from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.permissions import P
from app.core.tokenization import display_token
from app.detection.engine import DetectionEngine
from app.models import Alert, Disbursement, EnrollmentRecord, FinancialAidApplication, IdentityVerification, Student
from app.models.enums import (
    ApplicationStatus,
    AuditCategory,
    ReviewStatus,
    RiskLevel,
    VerificationStatus,
)
from app.schemas.aid import (
    ApplicationRow,
    EnrollmentOut,
    ReviewUpdate,
    StudentDetail,
    VerificationRow,
)
from app.schemas.common import Page, Pagination
from app.schemas.risk import ApplicationDetail
from app.services import audit, records, risk_views

router = APIRouter(prefix="/applications", tags=["applications"])

Reader = Annotated[Principal, Depends(require(P.APPLICATIONS_READ))]

_SORTS = {
    "submitted_at": FinancialAidApplication.submitted_at,
    "risk_score": FinancialAidApplication.risk_score,
    "reference": FinancialAidApplication.reference,
    "requested_amount": FinancialAidApplication.requested_amount,
}


@router.get("", response_model=Page[ApplicationRow], summary="Search, filter and sort applications")
def list_applications(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="Application or student reference")] = None,
    risk_level: Annotated[list[RiskLevel] | None, Query()] = None,
    status: ApplicationStatus | None = None,
    review_status: ReviewStatus | None = None,
    verification_status: VerificationStatus | None = None,
    scenario: Annotated[str | None, Query(max_length=40, description="Scenario key, 'any' or 'none'")] = None,
    institution_id: uuid.UUID | None = None,
    sort: Literal["submitted_at", "risk_score", "reference", "requested_amount"] = "risk_score",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[ApplicationRow]:
    stmt = scoped(select(FinancialAidApplication), FinancialAidApplication, principal)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.join(Student, Student.id == FinancialAidApplication.student_id).where(
            or_(func.lower(FinancialAidApplication.reference).like(like), func.lower(Student.student_ref).like(like))
        )
    if risk_level:
        stmt = stmt.where(FinancialAidApplication.risk_level.in_([r.value for r in risk_level]))
    if status:
        stmt = stmt.where(FinancialAidApplication.status == status.value)
    if review_status:
        stmt = stmt.where(FinancialAidApplication.review_status == review_status.value)
    if verification_status:
        stmt = stmt.where(FinancialAidApplication.verification_status == verification_status.value)
    if scenario == "any":
        stmt = stmt.where(FinancialAidApplication.scenario_key.is_not(None))
    elif scenario == "none":
        stmt = stmt.where(FinancialAidApplication.scenario_key.is_(None))
    elif scenario:
        stmt = stmt.where(FinancialAidApplication.scenario_key == scenario)
    if institution_id:
        stmt = stmt.where(FinancialAidApplication.organization_id == institution_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = _SORTS[sort]
    order = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_last()
    rows = db.scalars(
        stmt.order_by(order, FinancialAidApplication.reference).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(
        items=records.application_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/{application_id}", response_model=ApplicationDetail, summary="Application detail with related records")
def get_application(application_id: uuid.UUID, db: DB, principal: Reader) -> ApplicationDetail:
    app = get_scoped_or_404(db, FinancialAidApplication, application_id, principal, "Application")
    return build_detail(db, app, principal)


def build_detail(db: DB, app: FinancialAidApplication, principal: Principal) -> ApplicationDetail:
    stu = app.student
    row = records.application_rows(db, [app])[0]
    disbursements = db.scalars(
        select(Disbursement).where(Disbursement.student_id == stu.id).order_by(Disbursement.disbursed_at.desc())
    ).all()
    verifications = db.scalars(
        select(IdentityVerification)
        .where(IdentityVerification.student_id == stu.id)
        .order_by(IdentityVerification.created_at.desc())
    ).all()
    enrollments = db.scalars(
        select(EnrollmentRecord).where(EnrollmentRecord.student_id == stu.id).order_by(EnrollmentRecord.term_start)
    ).all()
    alerts = db.scalars(select(Alert).where(Alert.application_id == app.id).order_by(Alert.created_at.desc())).all()
    return ApplicationDetail(
        **row.model_dump(),
        assessment=risk_views.current_assessment(db, app.id),
        assessment_history=risk_views.assessment_history(db, app.id),
        alerts=risk_views.alert_rows(db, list(alerts)),
        dependency_status=app.dependency_status,
        enrollment_intensity=app.enrollment_intensity,
        program=app.program,
        student_aid_index=app.student_aid_index,
        submission_channel=app.submission_channel,
        device_handle=display_token(app.device_token, "DEV") if app.device_token else None,
        ip_handle=display_token(app.ip_token, "NET") if app.ip_token else None,
        student_detail=StudentDetail(
            **records.student_ref(stu).model_dump(),
            birth_year=stu.birth_year,
            state_of_residence=stu.state_of_residence,
            biometric_consent=stu.biometric_consent,
            biometric_consent_at=stu.biometric_consent_at,
            identity_tokens=records.identity_tokens(db, stu, principal),
        ),
        enrollments=[EnrollmentOut.model_validate(e) for e in enrollments],
        disbursements=records.disbursement_rows(db, list(disbursements)),
        verifications=[VerificationRow.model_validate(v) for v in verifications],
        related=records.related_groups(db, app, principal),
    )


@router.patch("/{application_id}/review", response_model=ApplicationRow, summary="Record a human review decision")
def review_application(
    application_id: uuid.UUID,
    body: ReviewUpdate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.APPLICATIONS_REVIEW))],
) -> ApplicationRow:
    app = get_scoped_or_404(db, FinancialAidApplication, application_id, principal, "Application")
    before = {"review_status": app.review_status, "status": app.status}
    app.review_status = body.review_status
    if body.application_status:
        app.status = body.application_status
    audit.record(
        db,
        category=AuditCategory.APPLICATION,
        action="application.review",
        actor=principal.user,
        organization_id=app.organization_id,
        target_type="application",
        target_id=app.id,
        target_ref=app.reference,
        details={"before": before, "review_status": app.review_status, "status": app.status, "note": body.note},
        request=request,
    )
    db.commit()
    return records.application_rows(db, [app])[0]


@router.post("/{application_id}/assess", response_model=ApplicationDetail, summary="Re-run the risk assessment now")
def assess_application(
    application_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.APPLICATIONS_ASSESS))],
) -> ApplicationDetail:
    app = get_scoped_or_404(db, FinancialAidApplication, application_id, principal, "Application")
    assessment, changed, alert_created = (
        DetectionEngine(db).prepare().assess(app, triggered_by="user", user=principal.user)
    )
    audit.record(
        db,
        category=AuditCategory.DETECTION,
        action="application.assess",
        actor=principal.user,
        organization_id=app.organization_id,
        target_type="application",
        target_id=app.id,
        target_ref=app.reference,
        details={
            "score": assessment.score,
            "level": assessment.level,
            "changed": changed,
            "alert_created": alert_created,
        },
        request=request,
    )
    db.commit()
    return build_detail(db, app, principal)
