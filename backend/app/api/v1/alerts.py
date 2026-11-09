from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, AlertNote, FinancialAidApplication, StudentFinancialAccount, User
from app.models.enums import (
    AlertCategory,
    AlertStatus,
    AuditCategory,
    RiskLevel,
    SignalCategory,
    VerificationRequestTrigger,
)
from app.schemas.common import Page, Pagination
from app.schemas.risk import (
    AlertAssign,
    AlertDetail,
    AlertNoteCreate,
    AlertRow,
    AlertSummary,
    AlertTriage,
    AlertVerificationRequest,
)
from app.services import audit, risk_views, verification_requests

router = APIRouter(prefix="/alerts", tags=["alerts"])

Reader = Annotated[Principal, Depends(require(P.ALERTS_READ))]
_LIVE = [
    AlertStatus.OPEN,
    AlertStatus.ACKNOWLEDGED,
    AlertStatus.VERIFICATION_REQUESTED,
    AlertStatus.ESCALATED,
    AlertStatus.IN_INVESTIGATION,
]
_SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1}
CATEGORIES = {c.value for c in SignalCategory} | {c.value for c in AlertCategory}
# action -> (allowed current statuses, new status, note required)
TRANSITIONS: dict[str, tuple[set[str], AlertStatus, bool]] = {
    "acknowledge": ({AlertStatus.OPEN}, AlertStatus.ACKNOWLEDGED, False),
    "escalate": (
        {AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.VERIFICATION_REQUESTED},
        AlertStatus.ESCALATED,
        True,
    ),
    "resolve": (
        {
            AlertStatus.ACKNOWLEDGED,
            AlertStatus.VERIFICATION_REQUESTED,
            AlertStatus.ESCALATED,
            AlertStatus.IN_INVESTIGATION,
        },
        AlertStatus.RESOLVED,
        True,
    ),
    "false_positive": (
        {AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.VERIFICATION_REQUESTED, AlertStatus.ESCALATED},
        AlertStatus.FALSE_POSITIVE,
        True,
    ),
    "dismiss": ({AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED}, AlertStatus.DISMISSED, True),
    "reopen": ({AlertStatus.DISMISSED, AlertStatus.ACKNOWLEDGED, AlertStatus.FALSE_POSITIVE}, AlertStatus.OPEN, False),
}


@router.get("", response_model=Page[AlertRow], summary="Fraud alerts awaiting or under human review")
def list_alerts(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: Annotated[list[AlertStatus] | None, Query()] = None,
    severity: RiskLevel | None = None,
    category: Annotated[str | None, Query(max_length=32, pattern=r"^[a-z_]+$")] = None,
    kind: Literal["application", "account"] | None = None,
    assigned: Literal["me", "unassigned"] | None = None,
    account_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=60, description="Alert, application or account reference")] = None,
    sort: Literal["created_at", "risk_score"] = "created_at",
) -> Page[AlertRow]:
    stmt = scoped(select(Alert), Alert, principal)
    if status:
        stmt = stmt.where(Alert.status.in_([s.value for s in status]))
    if severity:
        stmt = stmt.where(Alert.severity == severity.value)
    if category:
        if category not in CATEGORIES:
            raise ValidationFailedError(
                "Unknown alert category.", details=[{"field": "category", "message": "unknown"}]
            )
        stmt = stmt.where(Alert.category == category)
    if kind:
        stmt = stmt.where(Alert.account_id.is_not(None) if kind == "account" else Alert.application_id.is_not(None))
    if assigned == "me":
        stmt = stmt.where(Alert.assigned_to_id == principal.user.id)
    elif assigned == "unassigned":
        stmt = stmt.where(Alert.assigned_to_id.is_(None))
    if account_id:
        stmt = stmt.where(Alert.account_id == account_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = (
            stmt.outerjoin(FinancialAidApplication, FinancialAidApplication.id == Alert.application_id)
            .outerjoin(StudentFinancialAccount, StudentFinancialAccount.id == Alert.account_id)
            .where(
                or_(
                    func.lower(Alert.reference).like(like),
                    func.lower(FinancialAidApplication.reference).like(like),
                    func.lower(StudentFinancialAccount.reference).like(like),
                )
            )
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
    mine = db.scalar(
        scoped(select(func.count()).select_from(Alert), Alert, principal).where(
            Alert.assigned_to_id == principal.user.id, Alert.status.in_(_LIVE)
        )
    )
    return AlertSummary(
        open=by_status.get(AlertStatus.OPEN, 0),
        acknowledged=by_status.get(AlertStatus.ACKNOWLEDGED, 0),
        in_investigation=by_status.get(AlertStatus.IN_INVESTIGATION, 0),
        critical_open=critical_open or 0,
        by_category=by_category,
        verification_requested=by_status.get(AlertStatus.VERIFICATION_REQUESTED, 0),
        escalated=by_status.get(AlertStatus.ESCALATED, 0),
        by_status=by_status,
        assigned_to_me=mine or 0,
    )


@router.get("/{alert_id}", response_model=AlertDetail, summary="Alert with its explainable assessment")
def get_alert(alert_id: uuid.UUID, db: DB, principal: Reader) -> AlertDetail:
    return risk_views.alert_detail(db, get_scoped_or_404(db, Alert, alert_id, principal, "Alert"))


def _record(db: DB, alert: Alert, principal: Principal, action: str, request: Request, **details: object) -> None:
    audit.record(
        db,
        category=AuditCategory.INVESTIGATION,
        action=action,
        actor=principal.user,
        organization_id=alert.organization_id,
        target_type="alert",
        target_id=alert.id,
        target_ref=alert.reference,
        details=details,
        request=request,
    )


Triager = Annotated[Principal, Depends(require(P.ALERTS_TRIAGE))]


@router.patch(
    "/{alert_id}",
    response_model=AlertDetail,
    summary="Review, escalate, resolve, mark false positive, dismiss or reopen an alert",
)
def triage_alert(alert_id: uuid.UUID, body: AlertTriage, request: Request, db: DB, principal: Triager) -> AlertDetail:
    alert = get_scoped_or_404(db, Alert, alert_id, principal, "Alert")
    allowed, target, note_required = TRANSITIONS[body.action]
    if alert.status not in allowed:
        verb = body.action.replace("_", " ")
        raise ConflictError(f"An alert that is '{alert.status.replace('_', ' ')}' cannot be marked: {verb}.")
    if note_required and (not body.note or len(body.note.strip()) < 5):
        raise ValidationFailedError(
            "Explain the decision for the record.",
            details=[
                {"field": "note", "message": f"At least 5 characters required to {body.action.replace('_', ' ')}"}
            ],
        )
    previous = alert.status
    alert.status = target
    alert.triage_note = body.note.strip() if body.note else alert.triage_note
    alert.triaged_by_id = principal.user.id
    alert.triaged_at = utcnow()
    _record(
        db, alert, principal, f"alert.{body.action}", request, **{"from": previous, "to": target, "note": body.note}
    )
    db.commit()
    return risk_views.alert_detail(db, alert)


@router.post("/{alert_id}/assign", response_model=AlertDetail, summary="Assign the alert to an officer (or unassign)")
def assign(alert_id: uuid.UUID, body: AlertAssign, request: Request, db: DB, principal: Triager) -> AlertDetail:
    alert = get_scoped_or_404(db, Alert, alert_id, principal, "Alert")
    if body.assigned_to_id is not None:
        user = db.get(User, body.assigned_to_id)
        if user is None or user.organization_id != alert.organization_id:
            raise NotFoundError("Assignee not found.")
        if not user.is_active or P.ALERTS_TRIAGE.value not in user.permission_keys:
            raise ConflictError("Assignee must be an active officer who can triage alerts.")
    alert.assigned_to_id = body.assigned_to_id
    _record(
        db,
        alert,
        principal,
        "alert.assign",
        request,
        assigned_to_id=str(body.assigned_to_id) if body.assigned_to_id else None,
    )
    db.commit()
    return risk_views.alert_detail(db, alert)


@router.post("/{alert_id}/notes", response_model=AlertDetail, summary="Add an investigation note (append-only)")
def add_note(alert_id: uuid.UUID, body: AlertNoteCreate, request: Request, db: DB, principal: Triager) -> AlertDetail:
    alert = get_scoped_or_404(db, Alert, alert_id, principal, "Alert")
    db.add(
        AlertNote(
            organization_id=alert.organization_id,
            alert_id=alert.id,
            author_id=principal.user.id,
            body=body.body.strip(),
        )
    )
    _record(db, alert, principal, "alert.note_add", request)
    db.commit()
    return risk_views.alert_detail(db, alert)


@router.post(
    "/{alert_id}/request-verification",
    response_model=AlertDetail,
    summary="Request identity re-verification for the alert's student",
)
def request_verification(
    alert_id: uuid.UUID,
    body: AlertVerificationRequest,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.ALERTS_TRIAGE, P.VERIFICATIONS_INITIATE))],
) -> AlertDetail:
    alert = get_scoped_or_404(db, Alert, alert_id, principal, "Alert")
    if alert.status not in _LIVE:
        raise ConflictError("Reopen the alert before requesting verification.")
    account = db.get(StudentFinancialAccount, alert.account_id) if alert.account_id else None
    if account is None and alert.application_id:
        app = db.get(FinancialAidApplication, alert.application_id)
        account = db.scalar(
            select(StudentFinancialAccount).where(StudentFinancialAccount.student_id == app.student_id)  # type: ignore[union-attr]
        )
    if account is None:
        raise ConflictError("This alert is not linked to a student financial aid account.")
    req = verification_requests.create(
        db,
        account=account,
        trigger=VerificationRequestTrigger.OFFICER_REQUEST,
        reason=body.reason,
        actor=principal.user,
        alert=alert,
        request=request,
    )
    _record(db, alert, principal, "alert.request_verification", request, verification_request=req.reference)
    db.commit()
    return risk_views.alert_detail(db, alert)
