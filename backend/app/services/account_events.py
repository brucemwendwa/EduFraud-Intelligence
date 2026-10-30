"""Ingestion of authorised provider events: card transactions and account-security events.

Raw identifiers that arrive with an event (device fingerprint, session id, IP address, external
payout account, merchant id) exist only in memory here: each is HMAC-tokenized before anything
is stored. Locations are kept at city/country granularity, exactly as the provider reports them.

Every ingested event re-scores the student's account (see services.accounts.reassess) unless the
caller is bulk-loading history and scores once at the end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tokenization import TokenType, tokenize
from app.db.types import utcnow
from app.detection.account_engine import load_snapshot, score_transaction
from app.detection.account_rules import HIGH_RISK_MERCHANT_CATEGORIES
from app.models import (
    Device,
    PaymentDestinationToken,
    SecurityEvent,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    User,
)
from app.models.enums import AccountStatus, CardStatus, DeviceTrust, RiskLevel, SecurityEventType, TransactionStatus
from app.services.references import next_reference

_E = SecurityEventType
SENSITIVE_EVENTS = frozenset(
    {
        _E.PASSWORD_RESET_REQUESTED,
        _E.PASSWORD_CHANGED,
        _E.ACCOUNT_RECOVERY_REQUESTED,
        _E.CONTACT_DETAILS_CHANGED,
        _E.AID_REDIRECT_REQUESTED,
        _E.CARD_REPLACEMENT_REQUESTED,
    }
)


@dataclass
class EventOutcome:
    """What EduShield tells the provider to do with the request that produced an event."""

    decision: str  # "allow" | "step_up" | "hold"
    reason: str


def destination_for(db: Session, raw_account: str, *, kind: str = "bank_account") -> PaymentDestinationToken:
    """Get-or-create the pseudonymous token for an external payout or transfer destination."""
    token = tokenize(TokenType.BANK_ACCOUNT, raw_account)
    dest = db.scalar(select(PaymentDestinationToken).where(PaymentDestinationToken.token_value == token))
    if dest is None:
        digits = "".join(ch for ch in raw_account if ch.isdigit())
        dest = PaymentDestinationToken(
            token_value=token, destination_type=kind, display_suffix=(digits[-2:] or "00"), first_seen_at=utcnow()
        )
        db.add(dest)
        db.flush()
    return dest


def device_for(
    db: Session,
    account: StudentFinancialAccount,
    raw_device: str,
    *,
    label: str,
    platform: str,
    at: datetime,
    kiosk: bool = False,
) -> tuple[Device, bool]:
    """Get-or-create this student's record of a device. Returns (device, first time seen)."""
    token = tokenize(TokenType.DEVICE, raw_device)
    device = db.scalar(select(Device).where(Device.student_id == account.student_id, Device.device_token == token))
    if device is not None:
        device.last_seen_at = max(device.last_seen_at, at)
        return device, False
    device = Device(
        organization_id=account.organization_id,
        student_id=account.student_id,
        device_token=token,
        label=label[:80],
        platform=platform[:24],
        trust_status=DeviceTrust.UNFAMILIAR,
        first_seen_at=at,
        last_seen_at=at,
        is_shared_kiosk=kiosk,
    )
    db.add(device)
    db.flush()
    return device, True


def add_security_event(
    db: Session,
    account: StudentFinancialAccount,
    event_type: str,
    *,
    at: datetime | None = None,
    outcome: str = "recorded",
    source: str = "edushield",
    device: Device | None = None,
    card: StudentIDCard | None = None,
    destination: PaymentDestinationToken | None = None,
    session_raw: str | None = None,
    ip_raw: str | None = None,
    city: str | None = None,
    country: str | None = None,
    details: dict[str, Any] | None = None,
    note: str | None = None,
    actor: User | None = None,
    provider_event_id: str | None = None,
    scenario_key: str | None = None,
) -> SecurityEvent:
    at = at or utcnow()
    event = SecurityEvent(
        organization_id=account.organization_id,
        student_id=account.student_id,
        account_id=account.id,
        device_id=device.id if device else None,
        card_id=card.id if card else None,
        destination_id=destination.id if destination else None,
        reference=next_reference(db, SecurityEvent, "SEV", 6),
        provider_event_id=provider_event_id,
        event_type=event_type,
        source=source,
        outcome=outcome,
        occurred_at=at,
        session_token=tokenize(TokenType.SESSION, session_raw) if session_raw else None,
        ip_token=tokenize(TokenType.IP, ip_raw) if ip_raw else None,
        location_city=city,
        location_country=country.upper() if country else None,
        details=details or {},
        note=note,
        actor_user_id=actor.id if actor else None,
        scenario_key=scenario_key,
        created_at=utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def ingest_security_event(
    db: Session,
    account: StudentFinancialAccount,
    *,
    event_type: str,
    occurred_at: datetime,
    outcome: str,
    device_raw: str | None = None,
    device_label: str = "Unrecognised device",
    platform: str = "unknown",
    session_raw: str | None = None,
    ip_raw: str | None = None,
    city: str | None = None,
    country: str | None = None,
    destination_raw: str | None = None,
    source: str = "identity_provider_sandbox",
    provider_event_id: str | None = None,
    details: dict[str, Any] | None = None,
    scenario_key: str | None = None,
    reassess: bool = True,
) -> tuple[SecurityEvent, EventOutcome]:
    """Records a sign-in / credential / payout event and returns the risk-based decision for it."""
    device, first_seen = (None, False)
    if device_raw:
        device, first_seen = device_for(db, account, device_raw, label=device_label, platform=platform, at=occurred_at)
    if event_type == _E.LOGIN_SUCCESS and device is not None and device.trust_status != DeviceTrust.TRUSTED:
        signed_in_before = db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.device_id == device.id,
                SecurityEvent.event_type.in_([_E.LOGIN_SUCCESS, _E.NEW_DEVICE_LOGIN]),
            )
        )
        if first_seen or signed_in_before is None:
            event_type = _E.NEW_DEVICE_LOGIN
    if device is not None and event_type == _E.MFA_PASSED and device.trust_status == DeviceTrust.UNFAMILIAR:
        device.trust_status, device.trust_reason = DeviceTrust.TRUSTED, "Confirmed by additional authentication"
    destination = destination_for(db, destination_raw) if destination_raw else None

    held = event_type in SENSITIVE_EVENTS and account.sensitive_actions_restricted
    if held:
        outcome = "blocked"
    event = add_security_event(
        db,
        account,
        event_type,
        at=occurred_at,
        outcome=outcome,
        source=source,
        device=device,
        destination=destination,
        session_raw=session_raw,
        ip_raw=ip_raw,
        city=city,
        country=country,
        details=details,
        provider_event_id=provider_event_id,
        scenario_key=scenario_key,
    )
    decision = EventOutcome("allow", "No elevated risk.")
    if reassess:
        from app.services.accounts import reassess as reassess_account

        result = reassess_account(db, account, triggered_by="security_event", at=occurred_at)
        event.risk_score, event.risk_level = result.evaluation.score, result.evaluation.level
        event.risk_indicators = [
            {"code": s.code, "title": s.title, "category": s.category, "points": s.points}
            for s in result.evaluation.signals
            if s.evidence.get("event") == event.reference
        ]
        decision = decide(account, event, result.evaluation.level)
    elif held:
        decision = EventOutcome("hold", "Sensitive actions are on hold pending identity verification.")
    event.details = {**event.details, "decision": decision.decision, "decision_reason": decision.reason}
    return event, decision


def decide(account: StudentFinancialAccount, event: SecurityEvent, level: str) -> EventOutcome:
    if event.event_type in SENSITIVE_EVENTS and account.sensitive_actions_restricted:
        return EventOutcome("hold", "Sensitive actions are on hold pending identity verification.")
    elevated = level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
    unfamiliar = event.device is not None and event.device.trust_status != DeviceTrust.TRUSTED
    if elevated and (
        event.event_type in SENSITIVE_EVENTS or event.event_type in (_E.NEW_DEVICE_LOGIN, _E.LOGIN_SUCCESS)
    ):
        return EventOutcome("step_up", "Additional authentication required: account risk is elevated.")
    if unfamiliar and event.event_type in SENSITIVE_EVENTS:
        return EventOutcome(
            "step_up", "Sensitive change from an unconfirmed device: additional authentication required."
        )
    return EventOutcome("allow", "No elevated risk.")


def ingest_transaction(
    db: Session,
    account: StudentFinancialAccount,
    *,
    provider_event_id: str,
    amount: Decimal,
    merchant_name: str,
    merchant_category: str,
    occurred_at: datetime,
    channel: str = "card_present",
    transaction_type: str = "purchase",
    merchant_raw: str | None = None,
    card: StudentIDCard | None = None,
    destination_raw: str | None = None,
    city: str | None = None,
    country: str | None = None,
    status: str | None = None,
    scenario_key: str | None = None,
    reassess: bool = True,
) -> Transaction:
    """Records a provider transaction event (idempotent on provider_event_id) and scores it."""
    existing = db.scalar(select(Transaction).where(Transaction.provider_event_id == provider_event_id))
    if existing is not None:
        return existing
    destination = destination_for(db, destination_raw) if destination_raw else None
    decline = None
    if card is not None and card.status != CardStatus.ACTIVE:
        decline = "Card is blocked at the provider"
    elif account.status in (AccountStatus.SUSPENDED, AccountStatus.CLOSED):
        decline = f"Account {account.status}"
    elif account.sensitive_actions_restricted and (
        transaction_type == "transfer_out" or merchant_category in HIGH_RISK_MERCHANT_CATEGORIES
    ):
        decline = "Held: money movement out of the account is restricted pending verification"
    txn = Transaction(
        organization_id=account.organization_id,
        account_id=account.id,
        card_id=card.id if card else None,
        student_id=account.student_id,
        reference=next_reference(db, Transaction, "TXN", 7),
        provider_event_id=provider_event_id,
        transaction_type=transaction_type,
        channel=channel,
        merchant_name=merchant_name[:120],
        merchant_category=merchant_category,
        merchant_token=tokenize(TokenType.MERCHANT, merchant_raw) if merchant_raw else None,
        destination_id=destination.id if destination else None,
        amount=amount,
        occurred_at=occurred_at,
        location_city=city if channel != "online" else None,
        location_country=(country.upper() if country else None) if channel != "online" else None,
        status=TransactionStatus.DECLINED if decline else (status or TransactionStatus.APPROVED),
        decline_reason=decline,
        risk_indicators=[],
        scenario_key=scenario_key,
    )
    db.add(txn)
    db.flush()
    if txn.status == TransactionStatus.APPROVED:
        account.last_transaction_at = max(filter(None, (account.last_transaction_at, occurred_at)))
    if reassess:
        score_transaction(load_snapshot(db, account, now=occurred_at), txn)
        from app.services.accounts import reassess as reassess_account

        reassess_account(db, account, triggered_by="transaction", at=occurred_at)
    return txn
