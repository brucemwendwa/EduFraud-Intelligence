"""Transaction Intelligence: provider transaction events with explainable risk indicators."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import String, cast, func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Alert, SecurityEvent, Student, StudentFinancialAccount, Transaction, User
from app.models.enums import AuditCategory, RiskLevel, TransactionReview, TransactionStatus
from app.schemas.accounts import TransactionDetail, TransactionReviewIn, TransactionRow, TransactionSummary
from app.schemas.common import Page, Pagination
from app.services import account_views, accounts, audit, risk_views

router = APIRouter(prefix="/transactions", tags=["transaction intelligence"])

Reader = Annotated[Principal, Depends(require(P.TRANSACTIONS_READ))]
_FLAGGED = (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)


@router.get("", response_model=Page[TransactionRow], summary="Monitored transactions from the payment provider")
def list_transactions(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="TXN-, SFA- or STU- reference, or merchant")] = None,
    risk_level: RiskLevel | None = None,
    flagged: bool | None = None,
    category: Annotated[str | None, Query(max_length=32, pattern=r"^[a-z_]+$")] = None,
    indicator: Annotated[str | None, Query(max_length=48, pattern=r"^[A-Z_]+$")] = None,
    status: TransactionStatus | None = None,
    review_status: TransactionReview | None = None,
    account_id: uuid.UUID | None = None,
    since: datetime | None = None,
    sort: Literal["occurred_at", "amount", "risk_score"] = "occurred_at",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[TransactionRow]:
    stmt = scoped(select(Transaction), Transaction, principal)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = (
            stmt.join(StudentFinancialAccount, StudentFinancialAccount.id == Transaction.account_id)
            .join(Student, Student.id == Transaction.student_id)
            .where(
                or_(
                    func.lower(Transaction.reference).like(like),
                    func.lower(StudentFinancialAccount.reference).like(like),
                    func.lower(Student.student_ref).like(like),
                    func.lower(Transaction.merchant_name).like(like),
                )
            )
        )
    if risk_level:
        stmt = stmt.where(Transaction.risk_level == risk_level.value)
    if flagged is not None:
        stmt = stmt.where(Transaction.risk_level.in_(_FLAGGED) if flagged else Transaction.risk_level.not_in(_FLAGGED))
    if category:
        stmt = stmt.where(Transaction.merchant_category == category)
    if indicator:
        # JSON containment differs per dialect; a quoted-code text match is portable and exact enough here.
        stmt = stmt.where(cast(Transaction.risk_indicators, String).like(f'%"{indicator}"%'))
    if status:
        stmt = stmt.where(Transaction.status == status.value)
    if review_status:
        stmt = stmt.where(Transaction.review_status == review_status.value)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if since:
        stmt = stmt.where(Transaction.occurred_at >= since)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = {
        "occurred_at": Transaction.occurred_at,
        "amount": Transaction.amount,
        "risk_score": Transaction.risk_score,
    }[sort]
    order = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_first()
    rows = db.scalars(
        stmt.order_by(order, Transaction.reference.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(
        items=account_views.transaction_rows(db, principal, list(rows)),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/summary", response_model=TransactionSummary, summary="Transaction monitoring summary (last 30 days)")
def summary(db: DB, principal: Reader) -> TransactionSummary:
    since = utcnow() - timedelta(days=30)
    base = scoped(select(Transaction), Transaction, principal).where(Transaction.occurred_at >= since)
    rows = db.execute(
        base.with_only_columns(
            Transaction.risk_level,
            Transaction.status,
            Transaction.review_status,
            Transaction.merchant_category,
            Transaction.risk_indicators,
            Transaction.amount,
        )
    ).all()
    flagged = [r for r in rows if r.risk_level in _FLAGGED]
    by_indicator: Counter[str] = Counter()
    for r in flagged:
        for ind in r.risk_indicators or []:
            by_indicator[ind.get("title", ind.get("code", "?"))] += 1
    return TransactionSummary(
        total=len(rows),
        flagged=len(flagged),
        declined=sum(1 for r in rows if r.status == TransactionStatus.DECLINED),
        unreviewed_flagged=sum(1 for r in flagged if r.review_status == TransactionReview.UNREVIEWED),
        by_indicator=dict(by_indicator.most_common(8)),
        by_category=dict(Counter(r.merchant_category for r in flagged).most_common(8)),
        amount_total=sum((r.amount for r in rows if r.status == TransactionStatus.APPROVED), Decimal("0")),
    )


def _detail(db: DB, principal: Principal, txn: Transaction) -> TransactionDetail:
    row = account_views.transaction_rows(db, principal, [txn])[0]
    account = db.get(StudentFinancialAccount, txn.account_id)
    recent = db.scalars(
        select(Transaction)
        .where(Transaction.account_id == txn.account_id, Transaction.id != txn.id)
        .where(Transaction.occurred_at <= txn.occurred_at + timedelta(days=2))
        .order_by(Transaction.occurred_at.desc())
        .limit(12)
    ).all()
    events = db.scalars(
        select(SecurityEvent)
        .where(
            SecurityEvent.student_id == txn.student_id,
            SecurityEvent.occurred_at >= txn.occurred_at - timedelta(hours=24),
            SecurityEvent.occurred_at <= txn.occurred_at + timedelta(hours=2),
        )
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(20)
    ).all()
    alerts = db.scalars(select(Alert).where(Alert.transaction_id == txn.id)).all()
    reviewer = db.get(User, txn.reviewed_by_id) if txn.reviewed_by_id else None
    return TransactionDetail(
        **row.model_dump(),
        review_note=txn.review_note,
        reviewed_by=reviewer.full_name if reviewer else None,
        reviewed_at=txn.reviewed_at,
        account_status=account.status if account else "unknown",
        account_restricted=bool(account and account.sensitive_actions_restricted),
        recent_transactions=account_views.transaction_rows(db, principal, list(recent)),
        related_events=account_views.security_event_rows(db, principal, list(events)),
        alerts=risk_views.alert_rows(db, list(alerts)),
    )


@router.get("/{transaction_id}", response_model=TransactionDetail, summary="Transaction with indicators and context")
def get_transaction(transaction_id: uuid.UUID, db: DB, principal: Reader) -> TransactionDetail:
    return _detail(db, principal, get_scoped_or_404(db, Transaction, transaction_id, principal, "Transaction"))


@router.post(
    "/{transaction_id}/review",
    response_model=TransactionDetail,
    summary="Record a human review decision (cleared or suspicious)",
)
def review(
    transaction_id: uuid.UUID,
    body: TransactionReviewIn,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.TRANSACTIONS_REVIEW))],
) -> TransactionDetail:
    txn = get_scoped_or_404(db, Transaction, transaction_id, principal, "Transaction")
    if txn.review_status == body.decision:
        raise ConflictError(f"This transaction is already marked {body.decision}.")
    previous = txn.review_status
    txn.review_status, txn.review_note = body.decision, body.note
    txn.reviewed_by_id, txn.reviewed_at = principal.user.id, utcnow()
    audit.record(
        db,
        category=AuditCategory.TRANSACTION,
        action="transaction.review",
        actor=principal.user,
        organization_id=txn.organization_id,
        target_type="transaction",
        target_id=txn.id,
        target_ref=txn.reference,
        details={"from": previous, "to": body.decision, "note": body.note},
        request=request,
    )
    account = db.get(StudentFinancialAccount, txn.account_id)
    if account is not None:
        accounts.reassess(db, account, triggered_by="user", user=principal.user)
    db.commit()
    return _detail(db, principal, txn)
