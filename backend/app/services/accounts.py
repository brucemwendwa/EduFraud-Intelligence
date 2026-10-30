"""Account protection: re-scoring, proportionate automatic safeguards and officer actions.

Automatic safeguards are deliberately narrow. When combined risk is high *and* comes from at
least two independent categories, one of which indicates account takeover, EduShield asks the
provider to hold sensitive changes (payout redirection, credential changes, card replacement,
money transfers out) and opens an identity re-verification request. Everyday card spending is
never stopped automatically, and no student is ever suspended by the engine: suspension is a
person's decision, carried out by the provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.db.types import utcnow
from app.detection.account_engine import AccountEvaluation, evaluate, load_snapshot, persist
from app.integrations.payment_provider import get_payment_provider
from app.models import Alert, RiskAssessment, StudentFinancialAccount, User, VerificationRequest
from app.models.enums import (
    AccountStatus,
    AuditCategory,
    SecurityEventType,
    VerificationRequestStatus,
    VerificationRequestTrigger,
)
from app.services import account_alerts, audit
from app.services.account_events import add_security_event

ENGINE_ACTOR = "system:account-risk-engine"
OPEN_REQUEST_STATUSES = (
    VerificationRequestStatus.PENDING,
    VerificationRequestStatus.IN_PROGRESS,
    VerificationRequestStatus.ADDITIONAL_INFO_REQUIRED,
    VerificationRequestStatus.ESCALATED,
)


@dataclass
class ReassessResult:
    evaluation: AccountEvaluation
    assessment: RiskAssessment
    changed: bool
    alert: Alert | None
    alert_created: bool
    safeguards: list[str] = field(default_factory=list)


def audit_account(
    db: Session,
    account: StudentFinancialAccount,
    action: str,
    *,
    actor: User | None,
    request: Request | None = None,
    category: AuditCategory = AuditCategory.ACCOUNT,
    target_type: str = "account",
    target_id: object = None,
    target_ref: str | None = None,
    **details: object,
) -> None:
    audit.record(
        db,
        category=category,
        action=action,
        actor=actor,
        actor_email=None if actor else ENGINE_ACTOR,
        organization_id=account.organization_id,
        target_type=target_type,
        target_id=target_id or account.id,  # type: ignore[arg-type]
        target_ref=target_ref or account.reference,
        details=details,
        request=request,
    )


def open_request(db: Session, student_id) -> VerificationRequest | None:  # type: ignore[no-untyped-def]
    return db.scalar(
        select(VerificationRequest)
        .where(VerificationRequest.student_id == student_id, VerificationRequest.status.in_(OPEN_REQUEST_STATUSES))
        .order_by(VerificationRequest.created_at.desc())
    )


def reassess(
    db: Session,
    account: StudentFinancialAccount,
    *,
    triggered_by: str,
    user: User | None = None,
    at: datetime | None = None,
    safeguards: bool = True,
) -> ReassessResult:
    at = at or utcnow()
    result = evaluate(load_snapshot(db, account, now=at))
    assessment, changed = persist(db, account, result, triggered_by=triggered_by, user=user, at=at)
    alert, created = account_alerts.upsert_for_account(db, account, assessment, result)
    out = ReassessResult(result, assessment, changed, alert, created)
    if safeguards and result.needs_protection:
        out.safeguards = apply_safeguards(db, account, result, alert, at=at)
    return out


def _trigger_for(result: AccountEvaluation) -> VerificationRequestTrigger:
    cats = result.categories
    if "aid_redirection" in cats:
        return VerificationRequestTrigger.AID_REDIRECTION_ATTEMPT
    if "account_recovery" in cats:
        return VerificationRequestTrigger.SUSPICIOUS_PASSWORD_RECOVERY
    if "device" in cats and "authentication" in cats:
        return VerificationRequestTrigger.ACCOUNT_TAKEOVER_INDICATORS
    if "device" in cats:
        return VerificationRequestTrigger.HIGH_RISK_DEVICE
    return VerificationRequestTrigger.MULTIPLE_FRAUD_SIGNALS


def apply_safeguards(
    db: Session, account: StudentFinancialAccount, result: AccountEvaluation, alert: Alert | None, *, at: datetime
) -> list[str]:
    from app.services import verification_requests

    actions: list[str] = []
    if not account.sensitive_actions_restricted and account.status in (
        AccountStatus.ACTIVE,
        AccountStatus.PENDING_VERIFICATION,
    ):
        reason = (
            f"Automatic step-up hold: combined risk {result.score:.0f}/100 across "
            f"{', '.join(sorted(c.replace('_', ' ') for c in result.categories))}."
        )
        restrict(db, account, reason=reason, actor=None, at=at)
        actions.append("sensitive_actions_restricted")
    if open_request(db, account.student_id) is None:
        verification_requests.create(
            db,
            account=account,
            trigger=_trigger_for(result),
            reason=f"Raised automatically: {result.explanation}"[:500],
            actor=None,
            alert=alert,
            at=at,
        )
        actions.append("verification_requested")
    return actions


# ---------------------------------------------------------------- officer / provider actions


def restrict(
    db: Session,
    account: StudentFinancialAccount,
    *,
    reason: str,
    actor: User | None,
    at: datetime | None = None,
    request: Request | None = None,
) -> None:
    if account.status in (AccountStatus.SUSPENDED, AccountStatus.CLOSED):
        raise ConflictError(f"The account is {account.status}; the provider already blocks it.")
    if account.sensitive_actions_restricted:
        raise ConflictError("Sensitive actions on this account are already restricted.")
    at = at or utcnow()
    ack = get_payment_provider().restrict_account(account.provider_account_token, reason)
    account.sensitive_actions_restricted = True
    account.restriction_reason, account.restricted_at = reason[:300], at
    account.status, account.status_reason = AccountStatus.RESTRICTED, reason[:300]
    account.status_changed_at, account.status_changed_by_id = at, actor.id if actor else None
    add_security_event(
        db,
        account,
        SecurityEventType.ACCOUNT_RESTRICTED,
        at=at,
        source="edushield",
        actor=actor,
        details={"provider_ack": ack.reference, "provider_mode": ack.mode},
        note=reason,
    )
    audit_account(
        db,
        account,
        "account.restrict",
        actor=actor,
        request=request,
        reason=reason,
        provider_ack=ack.reference,
        automatic=actor is None,
    )


def _verified_since(
    db: Session, account: StudentFinancialAccount, since: datetime | None
) -> VerificationRequest | None:
    stmt = select(VerificationRequest).where(
        VerificationRequest.student_id == account.student_id,
        VerificationRequest.status == VerificationRequestStatus.VERIFIED,
    )
    if since is not None:
        stmt = stmt.where(VerificationRequest.decided_at >= since)
    return db.scalar(stmt.order_by(VerificationRequest.decided_at.desc()))


def lift_restriction(
    db: Session,
    account: StudentFinancialAccount,
    *,
    reason: str,
    actor: User | None,
    request: Request | None = None,
    at: datetime | None = None,
) -> None:
    """Lifts a hold. Holds placed automatically or for a card/verification need a verified identity first."""
    if not account.sensitive_actions_restricted:
        raise ConflictError("This account has no restriction to lift.")
    pending = open_request(db, account.student_id)
    if pending is not None:
        raise ConflictError(f"Complete verification request {pending.reference} before lifting the restriction.")
    manual = account.status_changed_by_id is not None and not (account.restriction_reason or "").startswith("Card")
    if not manual and _verified_since(db, account, account.restricted_at) is None:
        raise ConflictError("This hold was placed for security reasons: verify the student's identity first.")
    at = at or utcnow()
    ack = get_payment_provider().lift_restriction(account.provider_account_token, reason)
    account.sensitive_actions_restricted = False
    account.restriction_reason = None
    if account.status == AccountStatus.RESTRICTED:
        account.status, account.status_reason = AccountStatus.ACTIVE, reason[:300]
        account.status_changed_at, account.status_changed_by_id = at, actor.id if actor else None
    add_security_event(
        db,
        account,
        SecurityEventType.ACCOUNT_RESTRICTION_LIFTED,
        at=at,
        actor=actor,
        note=reason,
        details={"provider_ack": ack.reference},
    )
    audit_account(
        db, account, "account.restriction_lift", actor=actor, request=request, reason=reason, provider_ack=ack.reference
    )


def suspend(
    db: Session, account: StudentFinancialAccount, *, reason: str, actor: User, request: Request | None = None
) -> None:
    """A person asks the provider to suspend the account. The engine never calls this."""
    if account.status in (AccountStatus.SUSPENDED, AccountStatus.CLOSED):
        raise ConflictError(f"The account is already {account.status}.")
    ack = get_payment_provider().suspend_account(account.provider_account_token, reason)
    at = utcnow()
    account.status, account.status_reason = AccountStatus.SUSPENDED, reason[:300]
    account.status_changed_at, account.status_changed_by_id = at, actor.id
    audit_account(
        db, account, "account.suspend", actor=actor, request=request, reason=reason, provider_ack=ack.reference
    )


def reactivate(
    db: Session, account: StudentFinancialAccount, *, reason: str, actor: User, request: Request | None = None
) -> None:
    if account.status != AccountStatus.SUSPENDED:
        raise ConflictError("Only a suspended account can be reactivated.")
    if _verified_since(db, account, account.status_changed_at) is None:
        raise ConflictError("Verify the student's identity before asking the provider to reactivate the account.")
    ack = get_payment_provider().reactivate_account(account.provider_account_token, reason)
    at = utcnow()
    account.status = AccountStatus.RESTRICTED if account.sensitive_actions_restricted else AccountStatus.ACTIVE
    account.status_reason, account.status_changed_at, account.status_changed_by_id = reason[:300], at, actor.id
    audit_account(
        db, account, "account.reactivate", actor=actor, request=request, reason=reason, provider_ack=ack.reference
    )
