from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Disbursement, Student
from app.models.enums import AuditCategory, DisbursementStatus, FundType
from app.schemas.aid import (
    DestinationUsage,
    DisbursementDetail,
    DisbursementRow,
    DisbursementSummary,
    HoldRequest,
)
from app.schemas.common import Page, Pagination
from app.services import audit, records

router = APIRouter(prefix="/disbursements", tags=["disbursements"])

Reader = Annotated[Principal, Depends(require(P.DISBURSEMENTS_READ))]
Holder = Annotated[Principal, Depends(require(P.DISBURSEMENTS_HOLD))]

FLAG_THRESHOLD = 30.0  # disbursement risk at or above "medium" is shown as flagged

_SORTS = {
    "disbursed_at": Disbursement.disbursed_at,
    "amount": Disbursement.amount,
    "risk_score": Disbursement.risk_score,
}


@router.get("", response_model=Page[DisbursementRow], summary="Monitor disbursements")
def list_disbursements(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="Disbursement or student reference")] = None,
    status: DisbursementStatus | None = None,
    fund_type: FundType | None = None,
    flagged: bool | None = None,
    min_amount: Annotated[Decimal | None, Query(ge=0)] = None,
    institution_id: uuid.UUID | None = None,
    sort: Literal["disbursed_at", "amount", "risk_score"] = "disbursed_at",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[DisbursementRow]:
    stmt = scoped(select(Disbursement), Disbursement, principal)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.join(Student, Student.id == Disbursement.student_id).where(
            or_(func.lower(Disbursement.reference).like(like), func.lower(Student.student_ref).like(like))
        )
    if status:
        stmt = stmt.where(Disbursement.status == status.value)
    if fund_type:
        stmt = stmt.where(Disbursement.fund_type == fund_type.value)
    if flagged is True:
        stmt = stmt.where(Disbursement.risk_score >= FLAG_THRESHOLD)
    elif flagged is False:
        stmt = stmt.where(or_(Disbursement.risk_score.is_(None), Disbursement.risk_score < FLAG_THRESHOLD))
    if min_amount is not None:
        stmt = stmt.where(Disbursement.amount >= min_amount)
    if institution_id:
        stmt = stmt.where(Disbursement.organization_id == institution_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = _SORTS[sort]
    order = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_last()
    rows = db.scalars(stmt.order_by(order, Disbursement.reference).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=records.disbursement_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/summary", response_model=DisbursementSummary, summary="Disbursement totals for the current scope")
def summary(db: DB, principal: Reader) -> DisbursementSummary:
    flagged = Disbursement.risk_score >= FLAG_THRESHOLD
    held = Disbursement.status == DisbursementStatus.HELD
    stmt = scoped(
        select(
            func.count(),
            func.coalesce(func.sum(Disbursement.amount), 0),
            func.coalesce(func.sum(case((flagged, 1), else_=0)), 0),
            func.coalesce(func.sum(case((flagged, Disbursement.amount), else_=0)), 0),
            func.coalesce(func.sum(case((held, 1), else_=0)), 0),
            func.coalesce(func.sum(case((held, Disbursement.amount), else_=0)), 0),
            func.coalesce(func.sum(case((Disbursement.status == DisbursementStatus.SCHEDULED, 1), else_=0)), 0),
        ).select_from(Disbursement),
        Disbursement,
        principal,
    )
    total, amount, f_count, f_amount, h_count, h_amount, scheduled = db.execute(stmt).one()
    return DisbursementSummary(
        total_count=total,
        total_amount=Decimal(str(amount)),
        flagged_count=f_count,
        flagged_amount=Decimal(str(f_amount)),
        held_count=h_count,
        held_amount=Decimal(str(h_amount)),
        scheduled_count=scheduled,
    )


@router.get("/{disbursement_id}", response_model=DisbursementDetail, summary="Disbursement detail")
def get_disbursement(disbursement_id: uuid.UUID, db: DB, principal: Reader) -> DisbursementDetail:
    d = get_scoped_or_404(db, Disbursement, disbursement_id, principal, "Disbursement")
    return _detail(db, d, principal)


def _detail(db: DB, d: Disbursement, principal: Principal) -> DisbursementDetail:
    same_dest = db.scalars(
        scoped(select(Disbursement), Disbursement, principal)
        .where(Disbursement.destination_id == d.destination_id, Disbursement.id != d.id)
        .order_by(Disbursement.disbursed_at.desc())
        .limit(25)
    ).all()
    student_rows = db.scalars(
        select(Disbursement)
        .where(Disbursement.student_id == d.student_id, Disbursement.id != d.id)
        .order_by(Disbursement.disbursed_at.desc())
    ).all()
    in_scope, other = records.destination_usage_counts(db, d.destination_id, principal)
    return DisbursementDetail(
        **records.disbursement_rows(db, [d])[0].model_dump(),
        destination_usage=DestinationUsage(
            students_in_scope=in_scope,
            students_other_institutions=other,
            first_seen_at=d.destination.first_seen_at,
        ),
        same_destination=records.disbursement_rows(db, list(same_dest)),
        student_disbursements=records.disbursement_rows(db, list(student_rows)),
    )


@router.post("/{disbursement_id}/hold", response_model=DisbursementDetail, summary="Hold a scheduled disbursement")
def hold(
    disbursement_id: uuid.UUID, body: HoldRequest, request: Request, db: DB, principal: Holder
) -> DisbursementDetail:
    d = get_scoped_or_404(db, Disbursement, disbursement_id, principal, "Disbursement")
    if d.status != DisbursementStatus.SCHEDULED:
        raise ConflictError(
            "Only scheduled disbursements can be held. Released funds require a recovery process via an investigation."
        )
    d.status = DisbursementStatus.HELD
    d.hold_reason = body.reason
    d.held_by_id = principal.user.id
    d.held_at = utcnow()
    audit.record(
        db,
        category=AuditCategory.DISBURSEMENT,
        action="disbursement.hold",
        actor=principal.user,
        organization_id=d.organization_id,
        target_type="disbursement",
        target_id=d.id,
        target_ref=d.reference,
        details={"reason": body.reason, "amount": str(d.amount)},
        request=request,
    )
    db.commit()
    return _detail(db, d, principal)


@router.post("/{disbursement_id}/release", response_model=DisbursementDetail, summary="Release a held disbursement")
def release(
    disbursement_id: uuid.UUID, body: HoldRequest, request: Request, db: DB, principal: Holder
) -> DisbursementDetail:
    d = get_scoped_or_404(db, Disbursement, disbursement_id, principal, "Disbursement")
    if d.status != DisbursementStatus.HELD:
        raise ConflictError("This disbursement is not on hold.")
    d.status = DisbursementStatus.SCHEDULED
    audit.record(
        db,
        category=AuditCategory.DISBURSEMENT,
        action="disbursement.release",
        actor=principal.user,
        organization_id=d.organization_id,
        target_type="disbursement",
        target_id=d.id,
        target_ref=d.reference,
        details={"reason": body.reason, "previous_hold_reason": d.hold_reason},
        request=request,
    )
    d.hold_reason = None
    d.held_by_id = None
    d.held_at = None
    db.commit()
    return _detail(db, d, principal)
