"""Student Identity Verification requests: on-campus and remote pathways with a full timeline."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, InvestigationCase, Student, StudentFinancialAccount, VerificationRequest
from app.models.enums import VerificationPathway, VerificationRequestStatus
from app.schemas.accounts import (
    VerificationCheckIn,
    VerificationDecisionIn,
    VerificationLivenessIn,
    VerificationRequestCreate,
    VerificationRequestDetail,
    VerificationRequestRow,
    VerificationRequestSummary,
    VerificationScheduleIn,
    VerificationStartIn,
)
from app.schemas.common import Page, Pagination, Schema
from app.services import account_views
from app.services import verification_requests as service

router = APIRouter(prefix="/verification-requests", tags=["identity verification"])

Reader = Annotated[Principal, Depends(require(P.VERIFICATIONS_READ))]
Initiator = Annotated[Principal, Depends(require(P.VERIFICATIONS_INITIATE))]
Decider = Annotated[Principal, Depends(require(P.VERIFICATIONS_DECIDE))]


class VerificationOptions(Schema):
    statuses: list[str]
    methods: dict[str, list[dict[str, str]]]
    office: str | None
    embassy_arrangements: dict[str, str]
    simulated_samples: list[dict[str, str]]


@router.get("", response_model=Page[VerificationRequestRow], summary="Verification requests")
def list_requests(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: Annotated[list[VerificationRequestStatus] | None, Query()] = None,
    pathway: VerificationPathway | None = None,
    q: Annotated[str | None, Query(max_length=60, description="VRQ-, STU- or SFA- reference")] = None,
    account_id: uuid.UUID | None = None,
) -> Page[VerificationRequestRow]:
    stmt = scoped(select(VerificationRequest), VerificationRequest, principal)
    if status:
        stmt = stmt.where(VerificationRequest.status.in_([s.value for s in status]))
    if pathway:
        stmt = stmt.where(VerificationRequest.pathway == pathway.value)
    if account_id:
        stmt = stmt.where(VerificationRequest.account_id == account_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = (
            stmt.join(Student, Student.id == VerificationRequest.student_id)
            .outerjoin(StudentFinancialAccount, StudentFinancialAccount.id == VerificationRequest.account_id)
            .where(
                or_(
                    func.lower(VerificationRequest.reference).like(like),
                    func.lower(Student.student_ref).like(like),
                    func.lower(StudentFinancialAccount.reference).like(like),
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(VerificationRequest.created_at.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(
        items=account_views.verification_request_rows(db, list(rows)),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/summary", response_model=VerificationRequestSummary)
def summary(db: DB, principal: Reader) -> VerificationRequestSummary:
    vr = VerificationRequest
    by_status = dict(db.execute(scoped(select(vr.status, func.count()).group_by(vr.status), vr, principal)).all())
    by_pathway = dict(db.execute(scoped(select(vr.pathway, func.count()).group_by(vr.pathway), vr, principal)).all())
    overdue = db.scalar(
        scoped(select(func.count()).select_from(vr), vr, principal).where(
            vr.status.in_(service.OPEN_STATUSES), vr.due_at < utcnow()
        )
    )
    return VerificationRequestSummary(
        by_status=by_status,
        by_pathway=by_pathway,
        open=sum(by_status.get(s, 0) for s in service.OPEN_STATUSES),
        overdue=overdue or 0,
    )


@router.get("/options", response_model=VerificationOptions, summary="Methods, office and arrangements in scope")
def options(db: DB, principal: Reader) -> VerificationOptions:
    from app.biometrics.simulated import TEST_SAMPLES as SAMPLES
    from app.models import Organization

    org = db.get(Organization, principal.org_id) if principal.org_id else None
    arrangements = service.EMBASSY_ARRANGEMENTS.get(org.slug, {}) if org else {}
    return VerificationOptions(
        statuses=["not_required", *[s.value for s in VerificationRequestStatus]],
        methods={
            pathway: [{"method": m, "label": service.METHOD_LABELS[m]} for m in methods]
            for pathway, methods in service.METHODS.items()
        },
        office=service.OFFICES.get(org.slug) if org else None,
        embassy_arrangements=arrangements,
        simulated_samples=[{"key": k, "label": v.label} for k, v in SAMPLES.items()],
    )


def _detail(db: DB, req: VerificationRequest) -> VerificationRequestDetail:
    return account_views.verification_request_detail(db, req)


def _done(db: DB, req: VerificationRequest) -> VerificationRequestDetail:
    db.commit()
    db.refresh(req)
    return _detail(db, req)


@router.get("/{request_id}", response_model=VerificationRequestDetail, summary="Request with its timeline")
def get_request(request_id: uuid.UUID, db: DB, principal: Reader) -> VerificationRequestDetail:
    return _detail(db, get_scoped_or_404(db, VerificationRequest, request_id, principal, "Verification request"))


@router.post(
    "",
    response_model=VerificationRequestDetail,
    status_code=201,
    summary="Request identity re-verification for a student",
)
def create(
    body: VerificationRequestCreate, request: Request, db: DB, principal: Initiator
) -> VerificationRequestDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, body.account_id, principal, "Account")
    alert = get_scoped_or_404(db, Alert, body.alert_id, principal, "Alert") if body.alert_id else None
    case = get_scoped_or_404(db, InvestigationCase, body.case_id, principal, "Case") if body.case_id else None
    if alert is not None and alert.student_id not in (None, account.student_id):
        raise ConflictError("The alert belongs to a different student.")
    req = service.create(
        db,
        account=account,
        trigger=body.trigger,
        reason=body.reason,
        actor=principal.user,
        alert=alert,
        case=case,
        request=request,
    )
    return _done(db, req)


def _load(db: DB, principal: Principal, request_id: uuid.UUID) -> VerificationRequest:
    return get_scoped_or_404(db, VerificationRequest, request_id, principal, "Verification request")


@router.post("/{request_id}/notify", response_model=VerificationRequestDetail, summary="Re-send the student notice")
def notify(request_id: uuid.UUID, request: Request, db: DB, principal: Initiator) -> VerificationRequestDetail:
    req = _load(db, principal, request_id)
    if req.status not in service.OPEN_STATUSES:
        raise ConflictError("This request is closed.")
    service.notify_student(db, req, actor=principal.user, request=request)
    return _done(db, req)


@router.post(
    "/{request_id}/schedule", response_model=VerificationRequestDetail, summary="Book the on-campus verification visit"
)
def schedule(
    request_id: uuid.UUID, body: VerificationScheduleIn, request: Request, db: DB, principal: Decider
) -> VerificationRequestDetail:
    req = _load(db, principal, request_id)
    if body.appointment_at.tzinfo is None:
        raise ValidationFailedError("Include a timezone in the appointment time.")
    service.schedule(
        db,
        req,
        appointment_at=body.appointment_at,
        location_note=body.location_note,
        actor=principal.user,
        request=request,
    )
    return _done(db, req)


@router.post("/{request_id}/start", response_model=VerificationRequestDetail, summary="Start a remote method")
def start(
    request_id: uuid.UUID, body: VerificationStartIn, request: Request, db: DB, principal: Decider
) -> VerificationRequestDetail:
    req = _load(db, principal, request_id)
    account = db.get(StudentFinancialAccount, req.account_id) if req.account_id else None
    service.start(db, req, method=body.method, note=body.note, actor=principal.user, account=account, request=request)
    return _done(db, req)


@router.post(
    "/{request_id}/checks",
    response_model=VerificationRequestDetail,
    summary="Record a verification step (document check, procedure, video session …)",
)
def record_check(
    request_id: uuid.UUID, body: VerificationCheckIn, request: Request, db: DB, principal: Decider
) -> VerificationRequestDetail:
    req = _load(db, principal, request_id)
    service.record_check(
        db, req, step=body.step, result=body.result, note=body.note, actor=principal.user, request=request
    )
    return _done(db, req)


@router.post(
    "/{request_id}/liveness",
    response_model=VerificationRequestDetail,
    summary="Run the provider liveness check (SIMULATED in this prototype; consent required)",
)
def liveness(
    request_id: uuid.UUID, body: VerificationLivenessIn, request: Request, db: DB, principal: Decider
) -> VerificationRequestDetail:
    from app.biometrics.provider import ConsentRequiredError
    from app.biometrics.simulated import TEST_SAMPLES as SAMPLES

    req = _load(db, principal, request_id)
    if body.sample_key not in SAMPLES:
        raise ValidationFailedError("Unknown simulated sample.")
    try:
        service.run_liveness(db, req, sample_key=body.sample_key, actor=principal.user, request=request)
    except ConsentRequiredError as exc:
        raise ConflictError("The student has not consented to biometric checks.") from exc
    return _done(db, req)


@router.post(
    "/{request_id}/decision",
    response_model=VerificationRequestDetail,
    summary="Record the outcome with a documented reason (verified can restore access)",
)
def decision(
    request_id: uuid.UUID, body: VerificationDecisionIn, request: Request, db: DB, principal: Decider
) -> VerificationRequestDetail:
    req = _load(db, principal, request_id)
    service.decide(
        db,
        req,
        outcome=VerificationRequestStatus(body.outcome),
        reason=body.reason.strip(),
        restore_access=body.restore_access,
        actor=principal.user,
        request=request,
    )
    return _done(db, req)
