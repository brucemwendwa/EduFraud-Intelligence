"""Signed webhooks for authorised provider events (sandbox payment and identity providers).

Providers sign the raw request body with HMAC-SHA256 using PROVIDER_WEBHOOK_SECRET and send
`X-Provider-Signature: sha256=<hex>`. Events are idempotent on `provider_event_id`. Raw device,
session, IP, card, merchant and payout identifiers are tokenized on arrival and never stored.
The response tells the provider what to do: allow, require step-up authentication, or hold.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import Field, ValidationError
from sqlalchemy import select

from app.api.deps import DB
from app.core.config import get_settings
from app.core.errors import NotFoundError, UnauthorizedError, ValidationFailedError
from app.core.tokenization import TokenType, tokenize
from app.db.types import utcnow
from app.models import SecurityEvent, StudentFinancialAccount, StudentIDCard
from app.models.enums import AuditCategory, AuditOutcome, SecurityEventType
from app.schemas.common import Schema
from app.services import audit
from app.services.account_events import ingest_security_event, ingest_transaction

router = APIRouter(prefix="/provider-events", tags=["provider events (sandbox)"])

_ELEVATED = ("medium", "high", "critical")


class TransactionEventIn(Schema):
    provider_event_id: str = Field(min_length=6, max_length=64)
    provider_account_id: str = Field(min_length=4, max_length=64, description="Provider's account reference")
    card_serial: str | None = Field(default=None, max_length=64)
    amount: Decimal = Field(gt=0, le=50_000)
    currency: Literal["USD"] = "USD"
    merchant_name: str = Field(min_length=2, max_length=120)
    merchant_category: str = Field(min_length=2, max_length=32, pattern=r"^[a-z_]+$")
    merchant_id: str | None = Field(default=None, max_length=64)
    channel: Literal["card_present", "online", "atm", "transfer"] = "card_present"
    transaction_type: Literal["purchase", "atm_withdrawal", "transfer_out", "refund"] = "purchase"
    occurred_at: datetime
    location_city: str | None = Field(default=None, max_length=80)
    location_country: str | None = Field(default=None, min_length=2, max_length=2)
    destination_account: str | None = Field(default=None, max_length=40)


class SecurityEventIn(Schema):
    provider_event_id: str = Field(min_length=6, max_length=64)
    provider_account_id: str = Field(min_length=4, max_length=64)
    event_type: SecurityEventType
    outcome: Literal["success", "failure", "challenged", "requested"] = "success"
    occurred_at: datetime
    device_id: str | None = Field(default=None, max_length=128)
    device_label: str = Field(default="Unrecognised device", max_length=80)
    platform: str = Field(default="unknown", max_length=24)
    session_id: str | None = Field(default=None, max_length=128)
    ip: str | None = Field(default=None, max_length=45)
    location_city: str | None = Field(default=None, max_length=80)
    location_country: str | None = Field(default=None, min_length=2, max_length=2)
    destination_account: str | None = Field(default=None, max_length=40)
    details: dict[str, Any] = Field(default_factory=dict)


class IngestResult(Schema):
    reference: str
    duplicate: bool
    decision: str
    reason: str
    status: str | None = None
    risk_score: float | None
    risk_level: str | None
    account_reference: str
    account_risk_score: float | None
    account_risk_level: str | None
    provider_mode: str = "sandbox"


def sign(body: bytes) -> str:
    key = get_settings().provider_webhook_secret.get_secret_value().encode()
    return "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()


async def signed_body(request: Request, x_provider_signature: Annotated[str | None, Header()] = None) -> bytes:
    body = await request.body()
    if not x_provider_signature or not hmac.compare_digest(sign(body), x_provider_signature):
        raise UnauthorizedError("Missing or invalid provider signature.")
    return body


Body = Annotated[bytes, Depends(signed_body)]


def _parse[M: Schema](model: type[M], body: bytes) -> M:
    try:
        payload = model.model_validate_json(body)
    except ValidationError as exc:
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationFailedError("Invalid provider event.", details=details) from exc
    occurred = payload.occurred_at  # type: ignore[attr-defined]
    if occurred.tzinfo is None:
        raise ValidationFailedError("occurred_at must include a timezone.")
    if occurred > utcnow() + timedelta(minutes=5):
        raise ValidationFailedError("occurred_at is in the future.")
    return payload


def _account(db: DB, provider_account_id: str) -> StudentFinancialAccount:
    token = tokenize(TokenType.PROVIDER_ACCOUNT, provider_account_id)
    account = db.scalar(select(StudentFinancialAccount).where(StudentFinancialAccount.provider_account_token == token))
    if account is None:
        raise NotFoundError("Unknown provider account.")
    return account


def _audit(
    db: DB, account: StudentFinancialAccount, action: str, reference: str, level: str | None, **details: Any
) -> None:
    if level in _ELEVATED:
        audit.record(
            db,
            category=AuditCategory.TRANSACTION if action.startswith("transaction") else AuditCategory.SECURITY,
            action=action,
            outcome=AuditOutcome.SUCCESS,
            actor_email="provider:sandbox-webhook",
            organization_id=account.organization_id,
            target_type="account",
            target_id=account.id,
            target_ref=reference,
            details={"risk_level": level, **details},
        )


@router.post("/transactions", response_model=IngestResult, summary="Ingest a card transaction event (signed)")
def transaction_event(body: Body, db: DB) -> IngestResult:
    event = _parse(TransactionEventIn, body)
    account = _account(db, event.provider_account_id)
    card = None
    if event.card_serial:
        card = db.scalar(
            select(StudentIDCard).where(
                StudentIDCard.card_token == tokenize(TokenType.CARD, event.card_serial),
                StudentIDCard.student_id == account.student_id,
            )
        )
        if card is None:
            raise NotFoundError("Unknown card for this account.")
    from app.models import Transaction

    duplicate = db.scalar(select(Transaction).where(Transaction.provider_event_id == event.provider_event_id))
    txn = duplicate or ingest_transaction(
        db,
        account,
        provider_event_id=event.provider_event_id,
        amount=event.amount,
        merchant_name=event.merchant_name,
        merchant_category=event.merchant_category,
        merchant_raw=event.merchant_id or event.merchant_name,
        occurred_at=event.occurred_at,
        channel=event.channel,
        transaction_type=event.transaction_type,
        card=card,
        destination_raw=event.destination_account,
        city=event.location_city,
        country=event.location_country,
    )
    if duplicate is None:
        _audit(
            db,
            account,
            "transaction.flagged",
            txn.reference,
            txn.risk_level,
            transaction=txn.reference,
            status=txn.status,
        )
    db.commit()
    hold = txn.status == "declined"
    return IngestResult(
        reference=txn.reference,
        duplicate=duplicate is not None,
        decision="hold" if hold else ("review" if txn.risk_level in ("high", "critical") else "allow"),
        reason=txn.decline_reason or ("Flagged for human review." if txn.risk_level in ("high", "critical") else "OK"),
        status=txn.status,
        risk_score=txn.risk_score,
        risk_level=txn.risk_level,
        account_reference=account.reference,
        account_risk_score=account.risk_score,
        account_risk_level=account.risk_level,
    )


@router.post("/security", response_model=IngestResult, summary="Ingest an account-security event (signed)")
def security_event(body: Body, db: DB) -> IngestResult:
    payload = _parse(SecurityEventIn, body)
    account = _account(db, payload.provider_account_id)
    duplicate = db.scalar(select(SecurityEvent).where(SecurityEvent.provider_event_id == payload.provider_event_id))
    if duplicate is not None:
        details = duplicate.details or {}
        return IngestResult(
            reference=duplicate.reference,
            duplicate=True,
            decision=details.get("decision", "allow"),
            reason=details.get("decision_reason", ""),
            risk_score=duplicate.risk_score,
            risk_level=duplicate.risk_level,
            account_reference=account.reference,
            account_risk_score=account.risk_score,
            account_risk_level=account.risk_level,
        )
    event, decision = ingest_security_event(
        db,
        account,
        event_type=payload.event_type,
        occurred_at=payload.occurred_at,
        outcome=payload.outcome,
        device_raw=payload.device_id,
        device_label=payload.device_label,
        platform=payload.platform,
        session_raw=payload.session_id,
        ip_raw=payload.ip,
        city=payload.location_city,
        country=payload.location_country,
        destination_raw=payload.destination_account,
        provider_event_id=payload.provider_event_id,
        details={k: v for k, v in payload.details.items() if isinstance(v, str | int | float | bool)},
    )
    _audit(
        db, account, f"security_event.{event.event_type}", event.reference, event.risk_level, decision=decision.decision
    )
    db.commit()
    return IngestResult(
        reference=event.reference,
        duplicate=False,
        decision=decision.decision,
        reason=decision.reason,
        status=event.outcome,
        risk_score=event.risk_score,
        risk_level=event.risk_level,
        account_reference=account.reference,
        account_risk_score=account.risk_score,
        account_risk_level=account.risk_level,
    )
