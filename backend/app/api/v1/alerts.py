from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, FinancialAidApplication
from app.models.enums import AlertStatus, AuditCategory, RiskLevel, SignalCategory
from app.schemas.common import Page, Pagination
from app.schemas.risk import AlertDetail, AlertRow, AlertSummary, AlertTriage
from app.services import audit, risk_views

router = APIRouter(prefix="/alerts", tags=["alerts"])

Reader = Annotated[Principal, Depends(require(P.ALERTS_READ))]
_LIVE = [AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_INVESTIGATION]
_SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1}


@router.get("", response_model=Page[AlertRow], summary="Fraud alerts awaiting or under human review")
def list_alerts(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: RiskLevel | None = None,
    category: SignalCategory | None = None,
    q: Annotated[str | None, Query(max_length=60, description="Alert or application reference")] = None,
    sort: Literal["created_at", "risk_score"] = "created_at",
) -> Page[AlertRow]:
    stmt = scoped(select(Alert), Alert, principal)
    if status:
        stmt = stmt.where(Alert.status.in_([s.value for s in status]))
    if severity:
        stmt = stmt.where(Alert.severity == severity.value)
    if category:
        stmt = stmt.where(Alert.category == category.value)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.outerjoin(FinancialAidApplication, FinancialAidApplication.id == Alert.application_id).where(
            or_(func.lower(Alert.reference).like(like), func.lower(FinancialAidApplication.reference).like(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = Alert.risk_score.desc().nulls_last() if sort == "risk_score" else Alert.created_at.desc()
    rows = db.scalars(stmt.order_by(order, Alert.reference.desc()).offset(paging.offset).limit(paging.page_size)).all()
    return Page(items=risk_views.alert_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size)


@router.get("/summary", response_model=AlertSummary, summary="Alert counts for the current scope")
def summary(db: DB, principal: Reader) -> AlertSummary:
    by_status = dict(
        db.execute(scoped(select(Alert.status, func.count()).group_by(Alert.status), Alert, principal)).all()
    )
    critical_open = db.scalar(
        scoped(select(func.count()).select_from(Alert), Alert, principal).where(
            Alert.severity == RiskLevel.CRITICAL, Alert.status.in_(_LIVE)
        )
    )
    by_category = dict(
        db.execute(
            scoped(
                select(Alert.category, func.count()).where(Alert.status.in_(_LIVE)).group_by(Alert.category),
                Alert,
                principal,
            )
        ).all()
    )
    return AlertSummary(
        open=by_status.get(AlertStatus.OPEN, 0),
        acknowledged=by_status.get(AlertStatus.ACKNOWLEDGED, 0),
        in_investigation=by_status.get(AlertStatus.IN_INVESTIGATION, 0),
        critical_open=critical_open or 0,
        by_category=by_category,
    )


@router.get("/{alert_id}", response_model=AlertDetail, summary="Alert with its explainable assessment")
def get_alert(alert_id: uuid.UUID, db: DB, principal: Reader) -> AlertDetail:
    return risk_views.alert_detail(db, get_scoped_or_404(db, Alert, alert_id, principal, "Alert"))


@router.patch("/{alert_id}", response_model=AlertDetail, summary="Acknowledge, dismiss or reopen an alert")
def triage_alert(
    alert_id: uuid.UUID,
    body: AlertTriage,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.ALERTS_TRIAGE))],
) -> AlertDetail:
    alert = get_scoped_or_404(db, Alert, alert_id, principal, "Alert")
    transitions = {
        "acknowledge": ({AlertStatus.OPEN}, AlertStatus.ACKNOWLEDGED),
        "dismiss": ({AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED}, AlertStatus.DISMISSED),
        "reopen": ({AlertStatus.DISMISSED, AlertStatus.ACKNOWLEDGED}, AlertStatus.OPEN),
    }
    allowed, target = transitions[body.action]
    if alert.status not in allowed:
        raise ConflictError(f"An alert that is '{alert.status.replace('_', ' ')}' cannot be {body.action}ed.")
    if body.action == "dismiss" and (not body.note or len(body.note.strip()) < 5):
        raise ValidationFailedError(
            "Explain why this alert is being dismissed.",
            details=[{"field": "note", "message": "At least 5 characters required to dismiss"}],
        )
    previous = alert.status
    alert.status = target
    alert.triage_note = body.note.strip() if body.note else alert.triage_note
    alert.triaged_by_id = principal.user.id
    alert.triaged_at = utcnow()
    audit.record(
        db,
        category=AuditCategory.INVESTIGATION,
        action=f"alert.{body.action}",
        actor=principal.user,
        organization_id=alert.organization_id,
        target_type="alert",
        target_id=alert.id,
        target_ref=alert.reference,
        details={"from": previous, "to": target, "note": body.note},
        request=request,
    )
    db.commit()
    return risk_views.alert_detail(db, alert)
