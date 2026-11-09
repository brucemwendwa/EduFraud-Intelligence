"""University ID card lifecycle: lost/stolen reports, provider blocks, replacements and account links.

The card is only the credential that unlocks the provider-held account. Blocking and issuing are
performed by the payment provider (sandbox here); EduShield records the request and the
provider's acknowledgement. A blocked card is never reactivated from EduShield — the student gets
a replacement once their identity has been re-verified.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.core.tokenization import TokenType, tokenize
from app.db.types import utcnow
from app.integrations.payment_provider import get_payment_provider
from app.models import StudentFinancialAccount, StudentIDCard, User, VerificationRequest
from app.models.enums import (
    AccountStatus,
    AuditCategory,
    CardStatus,
    SecurityEventType,
    VerificationRequestStatus,
    VerificationRequestTrigger,
)
from app.services import accounts, verification_requests
from app.services.account_events import add_security_event
from app.services.references import next_reference


def _audit(
    db: Session,
    card: StudentIDCard,
    account: StudentFinancialAccount,
    action: str,
    *,
    actor: User | None,
    request: Request | None,
    **details: object,
) -> None:
    accounts.audit_account(
        db,
        account,
        action,
        actor=actor,
        request=request,
        category=AuditCategory.CARD,
        target_type="card",
        target_id=card.id,
        target_ref=card.reference,
        **details,
    )


def account_for(db: Session, card: StudentIDCard) -> StudentFinancialAccount:
    account = db.get(StudentFinancialAccount, card.account_id) if card.account_id else None
    if account is None:
        account = db.scalar(
            select(StudentFinancialAccount).where(StudentFinancialAccount.student_id == card.student_id)
        )
    if account is None:
        raise ConflictError("This card is not linked to a financial aid account.")
    return account


def report_lost(
    db: Session,
    card: StudentIDCard,
    *,
    channel: str,
    note: str | None,
    actor: User | None,
    block: bool = True,
    at: datetime | None = None,
    request: Request | None = None,
    scenario_key: str | None = None,
) -> VerificationRequest:
    """Records a lost/stolen report, blocks the card via the provider and opens a verification request."""
    if card.status != CardStatus.ACTIVE:
        raise ConflictError(f"Card {card.reference} is already {card.status.replace('_', ' ')}.")
    at = at or utcnow()
    account = account_for(db, card)
    card.status, card.reported_lost_at, card.report_channel = CardStatus.REPORTED_LOST, at, channel
    add_security_event(
        db,
        account,
        SecurityEventType.CARD_REPORTED_LOST,
        at=at,
        source=channel,
        card=card,
        actor=actor,
        note=note,
        scenario_key=scenario_key,
    )
    _audit(db, card, account, "card.report_lost", actor=actor, request=request, channel=channel, note=note)
    if block:
        block_card(
            db, card, reason="Reported lost or stolen", actor=actor, at=at, request=request, scenario_key=scenario_key
        )
    if not account.sensitive_actions_restricted and account.status in (
        AccountStatus.ACTIVE,
        AccountStatus.PENDING_VERIFICATION,
    ):
        accounts.restrict(
            db,
            account,
            reason=f"Card {card.reference} reported lost: sensitive changes need identity verification",
            actor=actor,
            at=at,
            request=request,
        )
    req = verification_requests.create(
        db,
        account=account,
        trigger=VerificationRequestTrigger.CARD_REPORTED_LOST,
        reason=f"Card {card.reference} reported lost via {channel.replace('_', ' ')}. Verify identity before a "
        "replacement card or account changes are approved.",
        actor=actor,
        card=card,
        at=at,
        request=request,
    )
    accounts.reassess(db, account, triggered_by="card_event", user=actor, at=at)
    return req


def block_card(
    db: Session,
    card: StudentIDCard,
    *,
    reason: str,
    actor: User | None,
    at: datetime | None = None,
    request: Request | None = None,
    scenario_key: str | None = None,
) -> None:
    if card.status not in (CardStatus.ACTIVE, CardStatus.REPORTED_LOST):
        raise ConflictError(f"Card {card.reference} is {card.status.replace('_', ' ')} and cannot be blocked again.")
    at = at or utcnow()
    account = account_for(db, card)
    ack = get_payment_provider().block_card(card.card_token, reason)
    card.status, card.blocked_at, card.block_confirmation = CardStatus.BLOCKED, at, ack.reference
    add_security_event(
        db,
        account,
        SecurityEventType.CARD_BLOCKED,
        at=at,
        source="payment_provider_sandbox",
        card=card,
        actor=actor,
        note=reason,
        scenario_key=scenario_key,
        details={"provider_ack": ack.reference, "provider_mode": ack.mode},
    )
    _audit(
        db,
        card,
        account,
        "card.block",
        actor=actor,
        request=request,
        reason=reason,
        provider_ack=ack.reference,
        provider_mode=ack.mode,
    )


def record_suspicious_activity(
    db: Session, card: StudentIDCard, *, note: str, actor: User, request: Request | None = None
) -> None:
    account = account_for(db, card)
    add_security_event(
        db, account, SecurityEventType.CARD_SUSPICIOUS_ACTIVITY, card=card, actor=actor, note=note, source="officer"
    )
    _audit(db, card, account, "card.suspicious_activity", actor=actor, request=request, note=note)
    accounts.reassess(db, account, triggered_by="card_event", user=actor)


def request_replacement(
    db: Session, card: StudentIDCard, *, note: str | None, actor: User | None, request: Request | None = None
) -> VerificationRequest:
    if card.status not in (CardStatus.REPORTED_LOST, CardStatus.BLOCKED):
        raise ConflictError("Report the card lost and block it before requesting a replacement.")
    at = utcnow()
    account = account_for(db, card)
    card.status, card.replacement_requested_at = CardStatus.REPLACEMENT_REQUESTED, at
    add_security_event(
        db,
        account,
        SecurityEventType.CARD_REPLACEMENT_REQUESTED,
        at=at,
        card=card,
        actor=actor,
        note=note,
        source="officer" if actor else "student_portal",
    )
    _audit(db, card, account, "card.replacement_request", actor=actor, request=request, note=note)
    req = verified_since_report(db, card) or verification_requests.create(
        db,
        account=account,
        trigger=VerificationRequestTrigger.CARD_REPORTED_LOST,
        reason=f"Replacement requested for {card.reference}: confirm identity before issuing a new card.",
        actor=actor,
        card=card,
        request=request,
    )
    accounts.reassess(db, account, triggered_by="card_event", user=actor)
    return req


def verified_since_report(db: Session, card: StudentIDCard) -> VerificationRequest | None:
    since = card.reported_lost_at or card.blocked_at
    stmt = select(VerificationRequest).where(
        VerificationRequest.student_id == card.student_id,
        VerificationRequest.status == VerificationRequestStatus.VERIFIED,
    )
    if since is not None:
        stmt = stmt.where(VerificationRequest.decided_at >= since)
    return db.scalar(stmt.order_by(VerificationRequest.decided_at.desc()))


def issue_replacement(
    db: Session, card: StudentIDCard, *, actor: User, request: Request | None = None
) -> StudentIDCard:
    """Provider issues a new card to the same account — only after identity was verified."""
    if card.status != CardStatus.REPLACEMENT_REQUESTED:
        raise ConflictError("A replacement must be requested first.")
    verified = verified_since_report(db, card)
    if verified is None:
        raise ConflictError("Identity must be re-verified before a replacement card is issued.")
    account = account_for(db, card)
    issued = get_payment_provider().issue_replacement(card.card_token, account.provider_account_token)
    at = utcnow()
    new = StudentIDCard(
        organization_id=card.organization_id,
        student_id=card.student_id,
        account_id=account.id,
        reference=next_reference(db, StudentIDCard, "CRD", 6),
        card_token=tokenize(TokenType.CARD, issued.serial),
        display_suffix=issued.serial[-4:],
        status=CardStatus.ACTIVE,
        issued_at=at,
        activated_at=at,
        expires_on=card.expires_on,
        is_synthetic=card.is_synthetic,
    )
    card.status = CardStatus.REPLACED
    db.add(new)
    db.flush()
    card.replaced_by_id = new.id
    add_security_event(
        db,
        account,
        SecurityEventType.CARD_REPLACED,
        at=at,
        card=new,
        actor=actor,
        source="payment_provider_sandbox",
        details={"provider_ack": issued.ack.reference, "replaces": card.reference, "verification": verified.reference},
    )
    _audit(
        db,
        new,
        account,
        "card.replace",
        actor=actor,
        request=request,
        replaces=card.reference,
        provider_ack=issued.ack.reference,
        verification=verified.reference,
    )
    accounts.reassess(db, account, triggered_by="card_event", user=actor)
    return new


def link_to_account(
    db: Session, card: StudentIDCard, account: StudentFinancialAccount, *, actor: User, request: Request | None = None
) -> None:
    if account.student_id != card.student_id:
        raise ConflictError("A card can only be linked to its own student's financial aid account.")
    if account.status in (AccountStatus.SUSPENDED, AccountStatus.CLOSED):
        raise ConflictError(f"The account is {account.status}; it cannot receive a card link.")
    if card.status != CardStatus.ACTIVE:
        raise ConflictError("Only an active card can be linked.")
    if card.account_id == account.id:
        raise ConflictError("The card is already linked to this account.")
    card.account_id = account.id
    _audit(db, card, account, "card.link", actor=actor, request=request, account=account.reference)
