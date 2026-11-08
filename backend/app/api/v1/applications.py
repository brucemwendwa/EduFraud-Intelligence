from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, require, scoped
from app.core.errors import ValidationFailedError
from app.core.permissions import P
from app.core.tokenization import display_token
from app.detection.engine import DetectionEngine
from app.models import (
    Alert,
    ApplicationStatusHistory,
    Disbursement,
    EnrollmentRecord,
    FinancialAidApplication,
    IdentityVerification,
    Student,
    User,
)
from app.models.enums import (
    ApplicationStatus,
    AuditCategory,
    ReviewStatus,
    RiskLevel,
    VerificationStatus,
)
from app.schemas.aid import (
    ApplicationHistoryItem,
    ApplicationRow,
    EnrollmentOut,
    ReviewUpdate,
    StudentDetail,
    VerificationRow,
)
from app.schemas.common import Page, Pagination
from app.schemas.risk import ApplicationDetail
from app.services import audit, records, risk_views
from app.services.application_lifecycle import (
    AWAITING_REVIEW,
    OPEN_FOR_REVIEW,
    REQUIRES_STUDENT_MESSAGE,
    change_status,
    require_staff_transition,
    staff_application_or_404,
    staff_targets,
)

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
    queue: Annotated[Literal["awaiting_review", "open"] | None, Query(description="Named work queue")] = None,
    review_status: ReviewStatus | None = None,
    verification_status: VerificationStatus | None = None,
    scenario: Annotated[str | None, Query(max_length=40, description="Scenario key, 'any' or 'none'")] = None,
    institution_id: uuid.UUID | None = None,
    sort: Literal["submitted_at", "risk_score", "reference", "requested_amount"] = "risk_score",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[ApplicationRow]:
    stmt = scoped(select(FinancialAidApplication), FinancialAidApplication, principal)
    stmt = stmt.where(FinancialAidApplication.submitted_at.is_not(None))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.join(Student, Student.id == FinancialAidApplication.student_id).where(
            or_(func.lower(FinancialAidApplication.reference).like(like), func.lower(Student.student_ref).like(like))
        )
    if risk_level:
        stmt = stmt.where(FinancialAidApplication.risk_level.in_([r.value for r in risk_level]))
    if status:
        stmt = stmt.where(FinancialAidApplication.status == status.value)
    if queue:
        members = AWAITING_REVIEW if queue == "awaiting_review" else OPEN_FOR_REVIEW
        stmt = stmt.where(FinancialAidApplication.status.in_([s.value for s in members]))
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
    return build_detail(db, staff_application_or_404(db, application_id, principal), principal)


def _status_history(db: DB, app: FinancialAidApplication) -> list[ApplicationHistoryItem]:
    rows = db.scalars(
        select(ApplicationStatusHistory)
        .where(ApplicationStatusHistory.application_id == app.id)
        .order_by(ApplicationStatusHistory.created_at.desc())
    ).all()
    actors = {r.actor_user_id for r in rows if r.actor_user_id}
    names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(actors))).all()) if actors else {}
    return [
        ApplicationHistoryItem(
            from_status=r.from_status,
            to_status=r.to_status,
            actor_name=names.get(r.actor_user_id),
            actor_role=r.actor_role,
            note=r.note,
            student_message=r.student_message,
            created_at=r.created_at,
        )
        for r in rows
    ]


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
        status_history=_status_history(db, app),
        allowed_status_changes=[s.value for s in staff_targets(app.status)],
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
    app = staff_application_or_404(db, application_id, principal)
    target = body.application_status
    if target in REQUIRES_STUDENT_MESSAGE and not body.student_message:
        raise ValidationFailedError(
            "Tell the student what is needed or why this decision was made.",
            details=[{"field": "student_message", "message": "Required for this decision."}],
        )
    if target:
        require_staff_transition(app.status, target)
    before = {"review_status": app.review_status, "status": app.status}
    app.review_status = body.review_status
    if target and target.value != app.status:
        change_status(
            db,
            app,
            to_status=target,
            actor=principal.user,
            request=request,
            action="application.status_change",
            note=body.note,
            student_message=body.student_message,
        )
    else:
        # A review with no status change still belongs on the staff timeline; students only see status changes.
        db.add(
            ApplicationStatusHistory(
                organization_id=app.organization_id,
                application_id=app.id,
                from_status=app.status,
                to_status=app.status,
                actor_user_id=principal.user.id,
                actor_role=principal.user.role.key,
                note=body.note,
            )
        )
    audit.record(
        db,
        category=AuditCategory.APPLICATION,
        action="application.review",
        actor=principal.user,
        organization_id=app.organization_id,
        target_type="application",
        target_id=app.id,
        target_ref=app.reference,
        details={
            "before": before,
            "review_status": app.review_status,
            "status": app.status,
            "note": body.note,
            "student_message": body.student_message,
        },
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
    app = staff_application_or_404(db, application_id, principal)
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
