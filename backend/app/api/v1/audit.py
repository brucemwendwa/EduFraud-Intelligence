from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, require
from app.core.permissions import P
from app.db.types import utcnow
from app.models import AuditEvent
from app.models.enums import AuditCategory, AuditOutcome
from app.schemas.audit import AuditEventOut, AuditSummary, ChainVerificationOut
from app.schemas.common import Page, Pagination
from app.services import audit

router = APIRouter(prefix="/audit", tags=["audit"])

Reader = Annotated[Principal, Depends(require(P.AUDIT_READ))]


def _scope(stmt, principal: Principal):  # type: ignore[no-untyped-def]
    # Institution users see their institution's events; platform-level events (no org) are platform-only.
    if principal.org_id is not None:
        stmt = stmt.where(AuditEvent.organization_id == principal.org_id)
    return stmt


@router.get("/events", response_model=Page[AuditEventOut], summary="Search the audit trail")
def list_events(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    category: AuditCategory | None = None,
    outcome: AuditOutcome | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Action, actor email or target reference")] = None,
    since: datetime | None = None,
    target_id: Annotated[str | None, Query(max_length=64)] = None,
) -> Page[AuditEventOut]:
    stmt = _scope(select(AuditEvent), principal)
    if category:
        stmt = stmt.where(AuditEvent.category == category.value)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome.value)
    if since:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if target_id:
        stmt = stmt.where(AuditEvent.target_id == target_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(AuditEvent.action).like(like),
                func.lower(AuditEvent.actor_email).like(like),
                func.lower(AuditEvent.target_ref).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditEvent.sequence.desc()).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=[AuditEventOut.model_validate(r) for r in rows], total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/summary", response_model=AuditSummary, summary="Audit activity overview")
def summary(db: DB, principal: Reader) -> AuditSummary:
    week_ago = utcnow() - timedelta(days=7)
    by_category = dict(
        db.execute(_scope(select(AuditEvent.category, func.count()).group_by(AuditEvent.category), principal)).all()
    )
    denied = db.scalar(
        _scope(select(func.count()).select_from(AuditEvent), principal).where(
            AuditEvent.outcome == AuditOutcome.DENIED, AuditEvent.occurred_at >= week_ago
        )
    )
    failed_logins = db.scalar(
        _scope(select(func.count()).select_from(AuditEvent), principal).where(
            AuditEvent.action == "auth.login",
            AuditEvent.outcome == AuditOutcome.FAILURE,
            AuditEvent.occurred_at >= week_ago,
        )
    )
    return AuditSummary(
        total_events=sum(by_category.values()),
        by_category=by_category,
        denied_last_7_days=denied or 0,
        failed_logins_last_7_days=failed_logins or 0,
    )


@router.get("/verify", response_model=ChainVerificationOut, summary="Verify the integrity of the audit hash chain")
def verify(request: Request, db: DB, principal: Reader) -> ChainVerificationOut:
    result = audit.verify_chain(db)
    audit.record(
        db,
        category=AuditCategory.SYSTEM,
        action="audit.chain_verified",
        outcome=AuditOutcome.SUCCESS if result.valid else AuditOutcome.FAILURE,
        actor=principal.user,
        details={"events_checked": result.events_checked, "valid": result.valid},
        request=request,
    )
    db.commit()
    return ChainVerificationOut(**result.__dict__)
