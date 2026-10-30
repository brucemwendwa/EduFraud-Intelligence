"""Student ID Card Management. Card controls are requests to the payment provider (sandbox here)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.permissions import P
from app.models import SecurityEvent, Student, StudentFinancialAccount, StudentIDCard, Transaction
from app.models.enums import CardStatus
from app.schemas.accounts import CardNoteIn, CardOut, LinkCardIn, ReportLostIn, SecurityEventRow, TransactionRow
from app.schemas.common import Page, Pagination, Schema
from app.services import account_views, cards

router = APIRouter(prefix="/cards", tags=["student id cards"])

Reader = Annotated[Principal, Depends(require(P.ACCOUNTS_READ))]
Manager = Annotated[Principal, Depends(require(P.CARDS_MANAGE))]


class CardDetail(CardOut):
    usage: list[TransactionRow]
    security_events: list[SecurityEventRow]
    history: list[CardOut]


class CardSummaryOut(Schema):
    by_status: dict[str, int]
    blocked_or_reported: int


@router.get("", response_model=Page[CardOut], summary="Registered student ID cards")
def list_cards(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="CRD-, STU- or SFA- reference")] = None,
    status: CardStatus | None = None,
    linked: bool | None = None,
    sort: Literal["issued_at", "reported_lost_at", "reference"] = "issued_at",
    direction: Literal["asc", "desc"] = "desc",
) -> Page[CardOut]:
    stmt = scoped(select(StudentIDCard), StudentIDCard, principal).join(Student, Student.id == StudentIDCard.student_id)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.outerjoin(StudentFinancialAccount, StudentFinancialAccount.id == StudentIDCard.account_id).where(
            or_(
                func.lower(StudentIDCard.reference).like(like),
                func.lower(Student.student_ref).like(like),
                func.lower(StudentFinancialAccount.reference).like(like),
            )
        )
    if status:
        stmt = stmt.where(StudentIDCard.status == status.value)
    if linked is not None:
        stmt = stmt.where(StudentIDCard.account_id.is_not(None) if linked else StudentIDCard.account_id.is_(None))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = {
        "issued_at": StudentIDCard.issued_at,
        "reported_lost_at": StudentIDCard.reported_lost_at,
        "reference": StudentIDCard.reference,
    }[sort]
    order = column.desc().nulls_last() if direction == "desc" else column.asc().nulls_first()
    rows = db.scalars(stmt.order_by(order, StudentIDCard.reference).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=account_views.card_rows(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size
    )


@router.get("/summary", response_model=CardSummaryOut)
def summary(db: DB, principal: Reader) -> CardSummaryOut:
    by_status = dict(
        db.execute(
            scoped(select(StudentIDCard.status, func.count()).group_by(StudentIDCard.status), StudentIDCard, principal)
        ).all()
    )
    flagged = sum(by_status.get(s, 0) for s in ("reported_lost", "blocked", "replacement_requested"))
    return CardSummaryOut(by_status=by_status, blocked_or_reported=flagged)


def _detail(db: DB, principal: Principal, card: StudentIDCard) -> CardDetail:
    usage = db.scalars(
        select(Transaction).where(Transaction.card_id == card.id).order_by(Transaction.occurred_at.desc()).limit(40)
    ).all()
    events = db.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.student_id == card.student_id, SecurityEvent.event_type.like("card_%"))
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(30)
    ).all()
    history = db.scalars(
        select(StudentIDCard)
        .where(StudentIDCard.student_id == card.student_id, StudentIDCard.id != card.id)
        .order_by(StudentIDCard.issued_at.desc())
    ).all()
    return CardDetail(
        **account_views.card_rows(db, [card])[0].model_dump(),
        usage=account_views.transaction_rows(db, principal, list(usage)),
        security_events=account_views.security_event_rows(db, principal, list(events)),
        history=account_views.card_rows(db, list(history)),
    )


def _done(db: DB, principal: Principal, card: StudentIDCard) -> CardDetail:
    db.commit()
    db.refresh(card)
    return _detail(db, principal, card)


@router.get("/{card_id}", response_model=CardDetail, summary="Card detail, usage history and card security events")
def get_card(card_id: uuid.UUID, db: DB, principal: Reader) -> CardDetail:
    return _detail(db, principal, get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card"))


@router.post(
    "/{card_id}/report-lost",
    response_model=CardDetail,
    summary="Record a lost/stolen report, block via the provider and open identity verification",
)
def report_lost(card_id: uuid.UUID, body: ReportLostIn, request: Request, db: DB, principal: Manager) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    cards.report_lost(
        db, card, channel=body.channel, note=body.note, actor=principal.user, block=body.block, request=request
    )
    return _done(db, principal, card)


@router.post("/{card_id}/block", response_model=CardDetail, summary="Ask the provider to block the card")
def block(card_id: uuid.UUID, body: CardNoteIn, request: Request, db: DB, principal: Manager) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    cards.block_card(db, card, reason=body.note, actor=principal.user, request=request)
    return _done(db, principal, card)


@router.post("/{card_id}/suspicious-activity", response_model=CardDetail, summary="Record suspicious card activity")
def suspicious(card_id: uuid.UUID, body: CardNoteIn, request: Request, db: DB, principal: Manager) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    cards.record_suspicious_activity(db, card, note=body.note, actor=principal.user, request=request)
    return _done(db, principal, card)


@router.post(
    "/{card_id}/request-replacement",
    response_model=CardDetail,
    summary="Request a replacement (identity verification is required before issue)",
)
def request_replacement(
    card_id: uuid.UUID, body: CardNoteIn, request: Request, db: DB, principal: Manager
) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    cards.request_replacement(db, card, note=body.note, actor=principal.user, request=request)
    return _done(db, principal, card)


@router.post(
    "/{card_id}/issue-replacement",
    response_model=CardDetail,
    summary="Provider issues the replacement card (only after verified identity)",
)
def issue_replacement(card_id: uuid.UUID, request: Request, db: DB, principal: Manager) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    new = cards.issue_replacement(db, card, actor=principal.user, request=request)
    return _done(db, principal, new)


@router.post("/{card_id}/link", response_model=CardDetail, summary="Link the card to an eligible aid account")
def link(card_id: uuid.UUID, body: LinkCardIn, request: Request, db: DB, principal: Manager) -> CardDetail:
    card = get_scoped_or_404(db, StudentIDCard, card_id, principal, "Card")
    account = get_scoped_or_404(db, StudentFinancialAccount, body.account_id, principal, "Account")
    cards.link_to_account(db, card, account, actor=principal.user, request=request)
    return _done(db, principal, card)
