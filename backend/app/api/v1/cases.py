"""Tenant-scoped, human-led investigation case management (business rules live in services/cases.py)."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, FinancialAidApplication, InvestigationCase, User
from app.models.enums import CaseDecisionType, CaseResolution, CaseStatus
from app.schemas.case import (
    AssigneeOut,
    CaseAlertRef,
    CaseApplicationRef,
    CaseAssign,
    CaseCreate,
    CaseDecisionIn,
    CaseDecisionOut,
    CaseDetail,
    CaseEvidenceCreate,
    CaseEvidenceOut,
    CaseNoteCreate,
    CaseNoteOut,
    CaseResolve,
    CaseRow,
    CaseSummary,
    CaseUpdate,
    TimelineEntryOut,
)
from app.schemas.common import Page, Pagination, UserRef
from app.services import cases as service
from app.services.records import mask_name

router = APIRouter(prefix="/cases", tags=["cases"])
Reader = Annotated[Principal, Depends(require(P.CASES_READ))]
Updater = Annotated[Principal, Depends(require(P.CASES_UPDATE))]


def _user_ref(user: User | None) -> UserRef | None:
    return UserRef.model_validate(user) if user else None


def _rows(db: DB, cases: list[InvestigationCase]) -> list[CaseRow]:
    app_refs = dict(
        db.execute(
            select(FinancialAidApplication.id, FinancialAidApplication.reference).where(
                FinancialAidApplication.id.in_({c.application_id for c in cases if c.application_id})
            )
        ).all()
    )
    now = utcnow()
    return [
        CaseRow(
            id=c.id,
            reference=c.reference,
            title=c.title,
            application_id=c.application_id,
            application_ref=app_refs.get(c.application_id),  # type: ignore[arg-type]
            fraud_category=c.fraud_category,
            priority=c.priority,
            status=c.status,
            finding=c.finding,
            risk_score_at_open=c.risk_score_at_open,
            assigned_to=_user_ref(c.assigned_to),
            created_by=_user_ref(c.created_by),
            due_at=c.due_at,
            overdue=bool(c.due_at and c.due_at < now and c.status in service.OPEN_STATUSES),
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in cases
    ]


def _detail(db: DB, case: InvestigationCase) -> CaseDetail:
    db.refresh(case)
    app = db.get(FinancialAidApplication, case.application_id) if case.application_id else None
    alerts = db.scalars(select(Alert).where(Alert.case_id == case.id).order_by(Alert.created_at)).all()
    return CaseDetail(
        **_rows(db, [case])[0].model_dump(),
        resolution=case.resolution,
        resolution_summary=case.resolution_summary,
        resolved_at=case.resolved_at,
        closed_at=case.closed_at,
        application=CaseApplicationRef(
            id=app.id,
            reference=app.reference,
            status=app.status,
            review_status=app.review_status,
            risk_score=app.risk_score,
            risk_level=app.risk_level,
            student_ref=app.student.student_ref,
            masked_name=mask_name(app.student.first_name, app.student.last_name),
        )
        if app
        else None,
        alerts=[CaseAlertRef.model_validate(a) for a in alerts],
        evidence=[CaseEvidenceOut.model_validate(e) for e in case.evidence],
        notes=[CaseNoteOut.model_validate(n) for n in case.notes],
        decisions=[CaseDecisionOut.model_validate(d) for d in case.decisions],
        timeline=[TimelineEntryOut(**t.__dict__) for t in service.timeline(db, case)],
    )


@router.get("", response_model=Page[CaseRow], summary="Investigation cases in the current scope")
def list_cases(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: Annotated[list[CaseStatus] | None, Query()] = None,
    assignee: Annotated[str | None, Query(max_length=40, description="'me', 'unassigned' or a user id")] = None,
    priority: Literal["low", "medium", "high", "urgent"] | None = None,
    finding: Annotated[
        str | None, Query(pattern="^(suspicious_activity|suspected_fraud|confirmed_fraud|not_substantiated)$")
    ] = None,
    q: Annotated[str | None, Query(max_length=100, description="Case or application reference, or title")] = None,
    sort: Literal["created_at", "due_at", "updated_at"] = "created_at",
) -> Page[CaseRow]:
    stmt = scoped(select(InvestigationCase), InvestigationCase, principal)
    if status:
        stmt = stmt.where(InvestigationCase.status.in_([s.value for s in status]))
    if assignee == "me":
        stmt = stmt.where(InvestigationCase.assigned_to_id == principal.user.id)
    elif assignee == "unassigned":
        stmt = stmt.where(InvestigationCase.assigned_to_id.is_(None))
    elif assignee:
        try:
            stmt = stmt.where(InvestigationCase.assigned_to_id == uuid.UUID(assignee))
        except ValueError as exc:
            raise ValidationFailedError("Unknown assignee filter.") from exc
    if priority:
        stmt = stmt.where(InvestigationCase.priority == priority)
    if finding:
        stmt = stmt.where(InvestigationCase.finding == finding)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.outerjoin(
            FinancialAidApplication, FinancialAidApplication.id == InvestigationCase.application_id
        ).where(
            or_(
                func.lower(InvestigationCase.reference).like(like),
                func.lower(InvestigationCase.title).like(like),
                func.lower(FinancialAidApplication.reference).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = getattr(InvestigationCase, sort)
    order = column.asc().nulls_last() if sort == "due_at" else column.desc()
    rows = db.scalars(
        stmt.order_by(order, InvestigationCase.reference.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(items=_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size)


@router.get("/summary", response_model=CaseSummary, summary="Case workload for the current scope")
def summary(db: DB, principal: Reader) -> CaseSummary:
    rows = db.execute(
        scoped(
            select(
                InvestigationCase.status,
                InvestigationCase.finding,
                InvestigationCase.assigned_to_id,
                InvestigationCase.due_at,
            ),
            InvestigationCase,
            principal,
        )
    ).all()
    now = utcnow()
    open_rows = [r for r in rows if r.status in service.OPEN_STATUSES]
    return CaseSummary(
        open=len(open_rows),
        unassigned=sum(1 for r in open_rows if r.assigned_to_id is None),
        escalated=sum(1 for r in rows if r.status == CaseStatus.ESCALATED),
        overdue=sum(1 for r in open_rows if r.due_at and r.due_at < now),
        resolved=sum(1 for r in rows if r.status in (CaseStatus.RESOLVED, CaseStatus.CLOSED)),
        by_finding=dict(Counter(r.finding for r in rows)),
    )


@router.get("/assignees", response_model=list[AssigneeOut], summary="People who can be assigned cases")
def assignees(
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_ASSIGN))],
    organization_id: uuid.UUID | None = None,
) -> list[AssigneeOut]:
    org_id = principal.org_id or organization_id or principal.user.organization_id
    users = db.scalars(
        select(User).where(User.organization_id == org_id, User.is_active).order_by(User.full_name)
    ).all()
    load = dict(
        db.execute(
            select(InvestigationCase.assigned_to_id, func.count())
            .where(InvestigationCase.status.in_(service.OPEN_STATUSES))
            .group_by(InvestigationCase.assigned_to_id)
        ).all()
    )
    return [
        AssigneeOut(id=u.id, full_name=u.full_name, email=u.email, title=u.title, open_cases=load.get(u.id, 0))
        for u in users
        if P.CASES_UPDATE.value in u.permission_keys
    ]


@router.get("/{case_id}", response_model=CaseDetail, summary="Case workspace: evidence, notes, decisions, timeline")
def get_case(case_id: uuid.UUID, db: DB, principal: Reader) -> CaseDetail:
    return _detail(db, get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case"))


@router.post("", response_model=CaseDetail, status_code=201, summary="Open a case from an alert or application")
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
    if body.assigned_to_id and not principal.can(P.CASES_ASSIGN):
        raise ConflictError("You can open a case but not assign it; an investigator will pick it up.")
    case = service.open_case(
        db,
        principal.user,
        app=app,
        alert=alert,
        title=body.title,
        fraud_category=body.fraud_category,
        priority=body.priority,
        assignee_id=body.assigned_to_id,
        due_at=body.due_at,
        request=request,
    )
    db.commit()
    return _detail(db, case)


@router.patch("/{case_id}", response_model=CaseDetail, summary="Edit details or start the review")
def update_case(case_id: uuid.UUID, body: CaseUpdate, request: Request, db: DB, principal: Updater) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    service.ensure_open(case, "edit it")
    changes = body.model_dump(exclude_unset=True)
    if changes.pop("status", None) == "under_review":
        service.start_review(db, case, principal.user, request)
    if changes:
        for field, value in changes.items():
            setattr(case, field, value.strip() if isinstance(value, str) else value)
        service.record_event(db, case, principal.user, "case.update", request, fields=",".join(sorted(changes)))
    db.commit()
    return _detail(db, case)


@router.post("/{case_id}/assign", response_model=CaseDetail, summary="Assign or reassign the case")
def assign_case(
    case_id: uuid.UUID,
    body: CaseAssign,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_ASSIGN))],
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    service.assign(db, case, principal.user, body.assigned_to_id, body.note, request)
    db.commit()
    return _detail(db, case)


@router.post("/{case_id}/notes", response_model=CaseDetail, summary="Add an internal note (append-only)")
def add_note(case_id: uuid.UUID, body: CaseNoteCreate, request: Request, db: DB, principal: Updater) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    service.add_note(db, case, principal.user, body.body, request)
    db.commit()
    return _detail(db, case)


@router.post("/{case_id}/evidence", response_model=CaseDetail, summary="Attach evidence (records are snapshotted)")
def add_evidence(
    case_id: uuid.UUID, body: CaseEvidenceCreate, request: Request, db: DB, principal: Updater
) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    service.add_evidence(
        db,
        case,
        principal.user,
        evidence_type=body.evidence_type,
        ref_id=body.ref_id,
        title=body.title,
        summary=body.summary,
        ref_label=body.ref_label,
        data=body.data,
        request=request,
    )
    db.commit()
    return _detail(db, case)


def _decide(db: DB, case_id: uuid.UUID, principal: Principal, request: Request, body: CaseDecisionIn) -> CaseDetail:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    if not body.acknowledged:
        raise ValidationFailedError(
            "Confirm that you reviewed the evidence and that this decision is your own.",
            details=[{"field": "acknowledged", "message": "Must be confirmed"}],
        )
    service.decide(
        db,
        case,
        principal.user,
        decision=CaseDecisionType(body.decision),
        outcome=body.outcome,
        justification=body.justification,
        request=request,
    )
    db.commit()
    return _detail(db, case)


@router.post(
    "/{case_id}/decision",
    response_model=CaseDetail,
    summary="Record a justified human decision: escalate, resolve (with outcome), reopen or close",
)
def record_decision(
    case_id: uuid.UUID,
    body: CaseDecisionIn,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_RESOLVE))],
) -> CaseDetail:
    return _decide(db, case_id, principal, request, body)


@router.post("/{case_id}/resolve", response_model=CaseDetail, deprecated=True, summary="Resolve (use /decision)")
def resolve_case(
    case_id: uuid.UUID,
    body: CaseResolve,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_RESOLVE))],
) -> CaseDetail:
    decision = CaseDecisionIn(
        decision="resolve", outcome=CaseResolution(body.resolution), justification=body.summary, acknowledged=True
    )
    return _decide(db, case_id, principal, request, decision)
