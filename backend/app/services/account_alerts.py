"""Turns account-protection assessments into alerts for human review (one live alert per account)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import P
from app.detection.account_engine import AccountEvaluation
from app.detection.account_rules import rule
from app.models import Alert, RiskAssessment, StudentFinancialAccount
from app.models.enums import AlertCategory, AlertStatus, RiskLevel, Severity
from app.services import notifications
from app.services.alerts import LIVE_STATUSES
from app.services.references import next_reference

_SEVERITY_RANK = {"medium": 1, "high": 2, "critical": 3}
_A = AlertCategory

TITLES = {
    _A.COORDINATED_FRAUD: "Coordinated activity across student accounts",
    _A.ACCOUNT_TAKEOVER: "Possible account takeover",
    _A.AID_REDIRECTION: "Attempt to redirect financial aid",
    _A.LOST_STOLEN_CARD: "Lost or stolen card used",
    _A.VERIFICATION_REQUIRED: "Identity verification required",
    _A.PASSWORD_RESET: "Suspicious password reset",
    _A.SUSPICIOUS_LOGIN: "Suspicious sign-in activity",
    _A.UNUSUAL_TRANSACTION: "Unusual transaction",
    _A.SUSPICIOUS_LOCATION: "Transaction in an unusual location",
    _A.NEW_DEVICE: "New device with other risk signals",
}
ACTIONS = {
    _A.COORDINATED_FRAUD: "Open an investigation and review every linked account in Fraud Network Intelligence.",
    _A.ACCOUNT_TAKEOVER: "Keep sensitive actions on hold and verify the student's identity through their pathway.",
    _A.AID_REDIRECTION: "Do not apply the payout change. Confirm the request with the student via a known channel.",
    _A.LOST_STOLEN_CARD: "Confirm the provider block and complete verification before issuing a replacement.",
    _A.VERIFICATION_REQUIRED: "Arrange identity re-verification before restoring sensitive actions.",
    _A.PASSWORD_RESET: "Require additional authentication; do not complete the reset until it is passed.",
    _A.SUSPICIOUS_LOGIN: "Require additional authentication on the next sign-in and review recent sessions.",
    _A.UNUSUAL_TRANSACTION: "Review the transaction evidence; contact the student before any restriction.",
    _A.SUSPICIOUS_LOCATION: "Check for travel or study abroad with the student before treating this as fraud.",
    _A.NEW_DEVICE: "Ask the student to confirm the device via additional authentication.",
}


def classify(result: AccountEvaluation) -> AlertCategory:
    codes = {s.code for s in result.signals}
    cats = result.categories
    if "DEVICE_SHARED_ACCOUNTS" in codes or "DESTINATION_SHARED_ACCOUNTS" in codes:
        return _A.COORDINATED_FRAUD
    if (
        result.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        and cats & {"account_recovery", "authentication"}
        and cats & {"device", "aid_redirection", "transaction"}
    ):
        return _A.ACCOUNT_TAKEOVER
    if "aid_redirection" in cats:
        return _A.AID_REDIRECTION
    if "TXN_AFTER_CARD_LOST" in codes or "card_security" in cats:
        return _A.LOST_STOLEN_CARD
    if "identity" in cats:
        return _A.VERIFICATION_REQUIRED
    if "account_recovery" in cats:
        return _A.PASSWORD_RESET
    if "authentication" in cats or "UNUSUAL_LOGIN_LOCATION" in codes:
        return _A.SUSPICIOUS_LOGIN
    if "transaction" in cats:
        return _A.UNUSUAL_TRANSACTION
    if "location" in cats:
        return _A.SUSPICIOUS_LOCATION
    return _A.NEW_DEVICE


def _alertable(result: AccountEvaluation) -> bool:
    """Medium or higher, backed by at least one non-contextual signal of medium severity or more."""
    if result.level == RiskLevel.LOW:
        return False
    return any(
        not rule(s.code).context_only and s.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        for s in result.signals
    )


def upsert_for_account(
    db: Session, account: StudentFinancialAccount, assessment: RiskAssessment, result: AccountEvaluation
) -> tuple[Alert | None, bool]:
    """Creates or refreshes the account's live alert. Returns (alert, created)."""
    if not _alertable(result):
        return None, False
    category = classify(result)
    dedupe_key = f"account:{account.id}:risk"
    links = {
        "transaction_id": result.riskiest_transaction.id if result.riskiest_transaction else None,
        "security_event_id": result.latest_event.id if result.latest_event else None,
        "card_id": (result.riskiest_transaction.card_id if result.riskiest_transaction else None),
    }
    existing = db.scalar(
        select(Alert)
        .where(Alert.dedupe_key == dedupe_key, Alert.status.in_(LIVE_STATUSES))
        .order_by(Alert.created_at.desc())
    )
    if existing is not None:
        existing.risk_score, existing.assessment_id, existing.summary = (
            assessment.score,
            assessment.id,
            result.explanation,
        )
        if _SEVERITY_RANK[result.level] > _SEVERITY_RANK.get(existing.severity, 0):
            existing.severity = result.level
            existing.category, existing.title = category, TITLES[category]
            existing.recommended_action = ACTIONS[category]
        for key, value in links.items():
            if value is not None:
                setattr(existing, key, value)
        return existing, False

    closed = db.scalar(select(Alert).where(Alert.dedupe_key == dedupe_key).order_by(Alert.created_at.desc()))
    if closed is not None and _SEVERITY_RANK[result.level] <= _SEVERITY_RANK.get(closed.severity, 0):
        return None, False  # a person already closed an alert at this level

    alert = Alert(
        organization_id=account.organization_id,
        reference=next_reference(db, Alert, "ALT", 5),
        category=category,
        severity=result.level,
        title=TITLES[category],
        summary=result.explanation,
        status=AlertStatus.OPEN,
        dedupe_key=dedupe_key,
        student_id=account.student_id,
        account_id=account.id,
        assessment_id=assessment.id,
        risk_score=assessment.score,
        recommended_action=ACTIONS[category],
        created_at=assessment.created_at,
        updated_at=assessment.created_at,
        **links,
    )
    db.add(alert)
    db.flush()
    if result.level == RiskLevel.CRITICAL:
        notifications.notify_permission_holders(
            db,
            organization_id=account.organization_id,
            permission=P.CASES_CREATE,
            kind="alert",
            title=f"Critical alert {alert.reference}: {alert.title}",
            body=f"{account.reference} scored {assessment.score:.0f}/100. Human review required.",
            link=f"/app/alerts?selected={alert.id}",
        )
    return alert, True
