"""Student Financial Aid Accounts: provider-held accounts accessed with the university ID card."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import exists, func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.models import (
    Disbursement,
    FinancialAidApplication,
    InvestigationCase,
    SecurityEvent,
    Student,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    VerificationRequest,
)
from app.models.enums import (
    AccountStatus,
    AuditCategory,
    CardStatus,
    DisbursementStatus,
    RiskLevel,
    VerificationRequestStatus,
)
from app.schemas.accounts import AccountDetail, AccountRow, AccountSummary, ReasonIn
from app.schemas.common import Page, Pagination
from app.services import account_views, accounts, audit
from app.services.verification_requests import OPEN_STATUSES

router = APIRouter(prefix="/accounts", tags=["student accounts"])
case_router = APIRouter(prefix="/cases", tags=["investigations"])

Reader = Annotated[Principal, Depends(require(P.ACCOUNTS_READ))]
Restrictor = Annotated[Principal, Depends(require(P.ACCOUNTS_RESTRICT))]


@router.get("", response_model=Page[AccountRow], summary="Student ID-linked financial aid accounts")
def list_accounts(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="SFA-, STU- or CRD- reference")] = None,
    status: AccountStatus | None = None,
    risk_level: RiskLevel | None = None,
    card_status: CardStatus | None = None,
    verification_status: Literal[
        "not_required", "pending", "in_progress", "verified", "failed", "escalated", "additional_info_required"
    ]
    | None = None,
    restricted: bool | None = None,
    sort: Literal["reference", "risk_score", "last_transaction_at", "allocated_total"] = "risk_score",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[AccountRow]:
    acct = StudentFinancialAccount
    stmt = scoped(select(acct), acct, principal).join(Student, Student.id == acct.student_id)
    if q:
        like = f"%{q.strip().lower()}%"
        card_match = exists().where(StudentIDCard.account_id == acct.id, func.lower(StudentIDCard.reference).like(like))
        stmt = stmt.where(
            or_(func.lower(acct.reference).like(like), func.lower(Student.student_ref).like(like), card_match)
        )
    if status:
        stmt = stmt.where(acct.status == status.value)
    if risk_level:
        stmt = stmt.where(acct.risk_level == risk_level.value)
    if restricted is not None:
        stmt = stmt.where(acct.sensitive_actions_restricted.is_(restricted))
    if card_status:
        stmt = stmt.where(
            exists().where(StudentIDCard.student_id == acct.student_id, StudentIDCard.status == card_status.value)
        )
    if verification_status:
        latest = (
            select(VerificationRequest.status)
            .where(VerificationRequest.student_id == acct.student_id)
            .order_by(VerificationRequest.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        stmt = stmt.where(latest.is_(None) if verification_status == "not_required" else latest == verification_status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    allocated = (
        select(func.coalesce(func.sum(Disbursement.amount), 0))
        .where(Disbursement.account_id == acct.id, Disbursement.status != DisbursementStatus.REVERSED)
        .scalar_subquery()
    )
    column = {
        "reference": acct.reference,
        "risk_score": acct.risk_score,
        "last_transaction_at": acct.last_transaction_at,
        "allocated_total": allocated,
    }[sort]
    order = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_first()
    rows = db.scalars(stmt.order_by(order, acct.reference).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=account_views.account_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/summary", response_model=AccountSummary, summary="Account, card and verification counts in scope")
def summary(db: DB, principal: Reader) -> AccountSummary:
    acct = StudentFinancialAccount
    by_status = dict(db.execute(scoped(select(acct.status, func.count()).group_by(acct.status), acct, principal)).all())
    by_risk = dict(
        db.execute(scoped(select(acct.risk_level, func.count()).group_by(acct.risk_level), acct, principal)).all()
    )
    restricted = db.scalar(
        scoped(select(func.count()).select_from(acct), acct, principal).where(acct.sensitive_actions_restricted)
    )
    allocated = db.scalar(
        scoped(select(func.coalesce(func.sum(Disbursement.amount), 0)), Disbursement, principal).where(
            Disbursement.account_id.is_not(None), Disbursement.status != DisbursementStatus.REVERSED
        )
    )
    cards = dict(
        db.execute(
            scoped(select(StudentIDCard.status, func.count()).group_by(StudentIDCard.status), StudentIDCard, principal)
        ).all()
    )
    open_requests = db.scalar(
        scoped(select(func.count()).select_from(VerificationRequest), VerificationRequest, principal).where(
            VerificationRequest.status.in_(OPEN_STATUSES)
        )
    )
    return AccountSummary(
        total=sum(by_status.values()),
        by_status=by_status,
        restricted=restricted or 0,
        by_risk={k or "unassessed": v for k, v in by_risk.items()},
        allocated_total=Decimal(allocated or 0),
        cards_by_status=cards,
        verification_open=open_requests or 0,
    )


@router.get("/{account_id}", response_model=AccountDetail, summary="Account workspace (access is audited)")
def get_account(account_id: uuid.UUID, request: Request, db: DB, principal: Reader) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    detail = account_views.account_detail(db, principal, account)
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="account.view",
        actor=principal.user,
        organization_id=account.organization_id,
        target_type="account",
        target_id=account.id,
        target_ref=account.reference,
        details={"location_visible": principal.can(P.LOCATION_READ)},
        request=request,
    )
    db.commit()
    return detail


def _act(db: DB, principal: Principal, account: StudentFinancialAccount) -> AccountDetail:
    db.commit()
    db.refresh(account)
    return account_views.account_detail(db, principal, account)


@router.post("/{account_id}/assess", response_model=AccountDetail, summary="Re-run the account risk assessment")
def assess(
    account_id: uuid.UUID, db: DB, principal: Annotated[Principal, Depends(require(P.DETECTION_RUN))]
) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    accounts.reassess(db, account, triggered_by="user", user=principal.user)
    return _act(db, principal, account)


@router.post(
    "/{account_id}/restrict",
    response_model=AccountDetail,
    summary="Ask the provider to hold sensitive changes (spending continues)",
)
def restrict(account_id: uuid.UUID, body: ReasonIn, request: Request, db: DB, principal: Restrictor) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    accounts.restrict(db, account, reason=body.reason, actor=principal.user, request=request)
    return _act(db, principal, account)


@router.post(
    "/{account_id}/lift-restriction",
    response_model=AccountDetail,
    summary="Lift a hold (security holds require a verified identity first)",
)
def lift_restriction(
    account_id: uuid.UUID, body: ReasonIn, request: Request, db: DB, principal: Restrictor
) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    accounts.lift_restriction(db, account, reason=body.reason, actor=principal.user, request=request)
    return _act(db, principal, account)


@router.post("/{account_id}/suspend", response_model=AccountDetail, summary="Ask the provider to suspend the account")
def suspend(account_id: uuid.UUID, body: ReasonIn, request: Request, db: DB, principal: Restrictor) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    accounts.suspend(db, account, reason=body.reason, actor=principal.user, request=request)
    return _act(db, principal, account)


@router.post(
    "/{account_id}/reactivate",
    response_model=AccountDetail,
    summary="Ask the provider to reactivate a suspended account (verified identity required)",
)
def reactivate(account_id: uuid.UUID, body: ReasonIn, request: Request, db: DB, principal: Restrictor) -> AccountDetail:
    account = get_scoped_or_404(db, StudentFinancialAccount, account_id, principal, "Account")
    accounts.reactivate(db, account, reason=body.reason, actor=principal.user, request=request)
    return _act(db, principal, account)


@case_router.get("/{case_id}/context", summary="Account, card, transaction and device context for a case")
def case_context(
    case_id: uuid.UUID,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.CASES_READ, P.ACCOUNTS_READ))],
) -> dict:
    case = get_scoped_or_404(db, InvestigationCase, case_id, principal, "Case")
    student_id = None
    if case.application_id:
        student_id = db.scalar(
            select(FinancialAidApplication.student_id).where(FinancialAidApplication.id == case.application_id)
        )
    if student_id is None:
        from app.models import Alert

        student_id = db.scalar(select(Alert.student_id).where(Alert.case_id == case.id, Alert.student_id.is_not(None)))
    account = (
        db.scalar(select(StudentFinancialAccount).where(StudentFinancialAccount.student_id == student_id))
        if student_id
        else None
    )
    if account is None:
        raise NotFoundError("No student ID-linked account is associated with this case.")
    flagged = db.scalars(
        select(Transaction)
        .where(Transaction.account_id == account.id, Transaction.risk_level.in_(["medium", "high", "critical"]))
        .order_by(Transaction.occurred_at.desc())
        .limit(20)
    ).all()
    events = db.scalars(
        select(SecurityEvent)
        .where(
            SecurityEvent.student_id == account.student_id, SecurityEvent.risk_level.in_(["medium", "high", "critical"])
        )
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(20)
    ).all()
    detail = account_views.account_detail(db, principal, account)
    open_request = next((r for r in detail.verification_requests if r.status in OPEN_STATUSES), None)
    return {
        "case_id": str(case.id),
        "account": account_views.account_rows(db, [account])[0].model_dump(mode="json"),
        "cards": [c.model_dump(mode="json") for c in detail.cards],
        "devices": [d.model_dump(mode="json") for d in detail.devices],
        "flagged_transactions": [
            t.model_dump(mode="json") for t in account_views.transaction_rows(db, principal, list(flagged))
        ],
        "security_events": [
            e.model_dump(mode="json") for e in account_views.security_event_rows(db, principal, list(events))
        ],
        "assessment": detail.assessment.model_dump(mode="json") if detail.assessment else None,
        "verification_status": detail.verification_status,
        "open_verification_request": open_request.model_dump(mode="json") if open_request else None,
        "verified": any(r.status == VerificationRequestStatus.VERIFIED for r in detail.verification_requests),
    }
