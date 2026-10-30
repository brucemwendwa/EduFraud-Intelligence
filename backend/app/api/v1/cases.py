"""Tenant-scoped, human-led investigation case management."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, CaseEvidence, CaseNote, FinancialAidApplication, InvestigationCase, User
from app.models.enums import AlertStatus, AuditCategory, CaseStatus
from app.schemas.case import (
    CaseAssign,
    CaseCreate,
    CaseDetail,
    CaseEvidenceCreate,
    CaseEvidenceOut,
    CaseNoteCreate,
    CaseNoteOut,
    CaseResolve,
    CaseRow,
    CaseUpdate,
)
from app.schemas.common import Page, Pagination, UserRef
from app.services import audit
from app.services.references import next_reference

router = APIRouter(prefix="/cases", tags=["investigations"])
Reader = Annotated[Principal, Depends(require(P.CASES_READ))]


def _user_ref(user: User | None) -> UserRef | None:
    return UserRef.model_validate(user) if user else None


def _row(case: InvestigationCase) -> CaseRow:
    return CaseRow(
        id=case.id,
        reference=case.reference,
        title=case.title,
        application_id=case.application_id,
        fraud_category=case.fraud_category,
        priority=case.priority,
        status=case.status,
        risk_score_at_open=case.risk_score_at_open,
        assigned_to=_user_ref(case.assigned_to),
        created_by=_user_ref(case.created_by),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _detail(case: InvestigationCase) -> CaseDetail:
    return CaseDetail(
        **_row(case).model_dump(),
        resolution=case.resolution,
        resolution_summary=case.resolution_summary,
        resolved_at=case.resolved_at,
        closed_at=case.closed_at,
        due_at=case.due_at,
        evidence=[CaseEvidenceOut.model_validate(item) for item in case.evidence],
        notes=[CaseNoteOut.model_validate(item) for item in case.notes],
    )


def _assignee(db: DB, principal: Principal, user_id: uuid.UUID | None) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or (principal.org_id is not None and user.organization_id != principal.org_id):
        raise NotFoundError("Assignee not found.")
    if not user.is_active or P.CASES_UPDATE.value not in user.permission_keys:
        raise ConflictError("Assignee must be an active investigator with case-update access.")
    return user


def _record(db: DB, case: InvestigationCase, actor: User, action: str, request: Request, **details: str | None) -> None:
    audit.record(
        db,
        category=AuditCategory.INVESTIGATION,
        action=action,
        actor=actor,
        organization_id=case.organization_id,
        target_type="case",
        target_id=case.id,
        target_ref=case.reference,
        details=details,
        request=request,
    )


@router.get("", response_model=Page[CaseRow])
def list_cases(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: str | None = Query(default=None, pattern="^(new|under_review|escalated|resolved|closed)$"),
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[CaseRow]:
    stmt = scoped(select(InvestigationCase), InvestigationCase, principal)
    if status:
        stmt = stmt.where(InvestigationCase.status == status)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(InvestigationCase.reference).like(like), func.lower(InvestigationCase.title).like(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(InvestigationCase.created_at.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(items=[_row(case) for case in rows], total=total, page=paging.page, page_size=paging.page_size)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(case_id: uuid.UUID, db: DB, principal: Reader) -> CaseDetail:
    return _detail(get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case"))


@router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    body: CaseCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_CREATE))],
) -> CaseDetail:
    if not body.application_id and not body.alert_id:
        raise ValidationFailedError("Choose an alert or application before opening a case.")
    app = (
        get_scoped_or_404(db, FinancialAidApplication, body.application_id, principal, "Application")
        if body.application_id
        else None
    )
    alert = get_scoped_or_404(db, Alert, body.alert_id, principal, "Alert") if body.alert_id else None
    if alert and alert.case_id:
        raise ConflictError("This alert is already linked to an investigation case.")
    if alert and app and alert.application_id and alert.application_id != app.id:
        raise ConflictError("The alert and application must refer to the same record.")
    app_id = app.id if app else alert.application_id  # alert exists when app does not
    org_id = app.organization_id if app else alert.organization_id  # type: ignore[union-attr]
    assignee = _assignee(db, principal, body.assigned_to_id)
    case = InvestigationCase(
        organization_id=org_id,
        reference=next_reference(db, InvestigationCase, "CASE", 5),
        title=body.title.strip(),
        application_id=app_id,
        fraud_category=body.fraud_category,
        priority=body.priority,
        risk_score_at_open=app.risk_score if app else alert.risk_score,
        assigned_to_id=assignee.id if assignee else None,
        created_by_id=principal.user.id,
        due_at=body.due_at,
    )
    db.add(case)
    db.flush()
    if alert:
        alert.case_id = case.id
        if alert.status in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED):
            alert.status = AlertStatus.IN_INVESTIGATION
    _record(db, case, principal.user, "case.create", request, alert_id=str(body.alert_id) if body.alert_id else None)
    db.commit()
    db.refresh(case)
    return _detail(case)


@router.patch("/{case_id}", response_model=CaseDetail)
def update_case(
    case_id: uuid.UUID,
    body: CaseUpdate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_UPDATE))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(case, field, value.strip() if isinstance(value, str) else value)
    _record(db, case, principal.user, "case.update", request, fields=",".join(sorted(changes)))
    db.commit()
    db.refresh(case)
    return _detail(case)


@router.post("/{case_id}/assign", response_model=CaseDetail)
def assign_case(
    case_id: uuid.UUID,
    body: CaseAssign,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_ASSIGN))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    assignee = _assignee(db, principal, body.assigned_to_id)
    case.assigned_to_id = assignee.id if assignee else None
    _record(
        db,
        case,
        principal.user,
        "case.assign",
        request,
        assigned_to_id=str(body.assigned_to_id) if body.assigned_to_id else None,
    )
    db.commit()
    db.refresh(case)
    return _detail(case)


@router.post("/{case_id}/notes", response_model=CaseDetail)
def add_note(
    case_id: uuid.UUID,
    body: CaseNoteCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_UPDATE))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    db.add(
        CaseNote(
            organization_id=case.organization_id,
            case_id=case.id,
            author_id=principal.user.id,
            body=body.body.strip(),
        )
    )
    _record(db, case, principal.user, "case.note_add", request)
    db.commit()
    db.refresh(case)
    return _detail(case)


@router.post("/{case_id}/evidence", response_model=CaseDetail)
def add_evidence(
    case_id: uuid.UUID,
    body: CaseEvidenceCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_UPDATE))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    db.add(
        CaseEvidence(
            organization_id=case.organization_id,
            case_id=case.id,
            added_by_id=principal.user.id,
            **body.model_dump(),
        )
    )
    _record(db, case, principal.user, "case.evidence_add", request, evidence_type=body.evidence_type)
    db.commit()
    db.refresh(case)
    return _detail(case)


@router.post("/{case_id}/resolve", response_model=CaseDetail)
def resolve_case(
    case_id: uuid.UUID,
    body: CaseResolve,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_RESOLVE))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    case.resolution, case.resolution_summary = body.resolution, body.summary.strip()
    case.resolved_at, case.status = utcnow(), CaseStatus.RESOLVED
    _record(db, case, principal.user, "case.resolve", request, resolution=body.resolution)
    db.commit()
    db.refresh(case)
    return _detail(case)
