"""Turns high-risk assessments into alerts for human triage (one live alert per application)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import P
from app.detection.signals import Signal
from app.models import Alert, FinancialAidApplication, RiskAssessment
from app.models.enums import AlertStatus, RiskLevel, SignalCategory
from app.services import notifications
from app.services.references import next_reference

LIVE_STATUSES = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_INVESTIGATION)
_SEVERITY_RANK = {"medium": 1, "high": 2, "critical": 3}


def classify(signals: list[Signal]) -> tuple[str, str]:
    """Alert category and headline from the most specific evidence present."""
    codes = {s.code for s in signals}
    if codes & {"FACE_MISMATCH", "PRESENTATION_ATTACK", "DOCUMENT_SUSPICIOUS"}:
        return SignalCategory.BIOMETRIC, "Possible identity impersonation"
    if "SSN_IDENTITY_CONFLICT" in codes:
        return SignalCategory.IDENTITY, "Duplicate or synthetic identity"
    if "NETWORK_CLUSTER" in codes and codes & {"DEVICE_BURST", "NETWORK_BURST"}:
        return SignalCategory.NETWORK, "Coordinated application network"
    if codes & {"AMOUNT_OUTLIER", "DISBURSEMENT_BURST"}:
        return SignalCategory.DISBURSEMENT, "Unusual disbursement activity"
    if "DESTINATION_SHARED" in codes:
        return SignalCategory.DISBURSEMENT, "Payment destination shared across students"
    if "NO_ATTENDANCE" in codes:
        return SignalCategory.ENROLLMENT, "Aid disbursed without attendance"
    if "NETWORK_CLUSTER" in codes:
        return SignalCategory.NETWORK, "Linked to a suspicious cluster"
    return SignalCategory.APPLICATION, "Elevated fraud risk"


def upsert_for_assessment(
    db: Session,
    app: FinancialAidApplication,
    assessment: RiskAssessment,
    signals: list[Signal],
    *,
    disbursement_id=None,  # type: ignore[no-untyped-def]
    verification_id=None,  # type: ignore[no-untyped-def]
) -> tuple[Alert | None, bool]:
    """Creates or refreshes the application's live alert. Returns (alert, created)."""
    if assessment.level not in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return None, False
    category, title = classify(signals)
    dedupe_key = f"application:{app.id}:risk"
    existing = db.scalar(
        select(Alert)
        .where(Alert.dedupe_key == dedupe_key, Alert.status.in_(LIVE_STATUSES))
        .order_by(Alert.created_at.desc())
    )
    if existing is not None:
        existing.risk_score = assessment.score
        existing.assessment_id = assessment.id
        existing.summary = assessment.explanation
        if _SEVERITY_RANK[assessment.level] > _SEVERITY_RANK.get(existing.severity, 0):
            existing.severity = assessment.level
            existing.category, existing.title = category, title
        existing.verification_id = verification_id or existing.verification_id
        existing.disbursement_id = disbursement_id or existing.disbursement_id
        return existing, False

    closed = db.scalar(select(Alert).where(Alert.dedupe_key == dedupe_key).order_by(Alert.created_at.desc()))
    if closed is not None and _SEVERITY_RANK[assessment.level] <= _SEVERITY_RANK.get(closed.severity, 0):
        return None, False  # a person already dismissed/resolved an alert at this level

    alert = Alert(
        organization_id=app.organization_id,
        reference=next_reference(db, Alert, "ALT", 5),
        category=category,
        severity=assessment.level,
        title=title,
        summary=assessment.explanation,
        status=AlertStatus.OPEN,
        dedupe_key=dedupe_key,
        application_id=app.id,
        disbursement_id=disbursement_id,
        verification_id=verification_id,
        assessment_id=assessment.id,
        risk_score=assessment.score,
    )
    db.add(alert)
    db.flush()
    if assessment.level == RiskLevel.CRITICAL:
        notifications.notify_permission_holders(
            db,
            organization_id=app.organization_id,
            permission=P.CASES_CREATE,
            kind="alert",
            title=f"Critical alert {alert.reference}: {title}",
            body=f"{app.reference} scored {assessment.score:.0f}/100. Human review required.",
            link=f"/app/alerts?selected={alert.id}",
        )
    return alert, True
