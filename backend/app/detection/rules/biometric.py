"""Biometric rules: failed step-up verifications (face mismatch, presentation attacks, suspicious documents)."""

from __future__ import annotations

from datetime import timedelta

from app.detection.context import DetectionContext
from app.detection.signals import Signal
from app.detection.versions import RULES_VERSION
from app.models import FinancialAidApplication
from app.models.enums import Severity, SignalCategory, VerificationOutcome

LOOKBACK = timedelta(days=90)
FACE_MISMATCH_THRESHOLD = 0.5


def evaluate(ctx: DetectionContext, app: FinancialAidApplication) -> list[Signal]:
    signals: list[Signal] = []
    history = [v for v in ctx.student_verifications.get(app.student_id, []) if ctx.now - v.created_at <= LOOKBACK]
    for v in history:
        if v.status != VerificationOutcome.FAILED:
            continue
        # A later successful verification by the account owner lowers, but does not erase, an attack attempt.
        resolved = any(
            later.status == VerificationOutcome.PASSED and later.created_at > v.created_at for later in history
        )
        factor = 0.5 if resolved else 1.0
        suffix = " Account owner later verified successfully." if resolved else ""
        evidence = {"verification": v.reference, "trigger": v.trigger, "provider_mode": v.provider_mode}

        if v.face_match_score is not None and v.face_match_score < FACE_MISMATCH_THRESHOLD:
            signals.append(
                Signal(
                    code="FACE_MISMATCH",
                    category=SignalCategory.BIOMETRIC,
                    severity=Severity.CRITICAL,
                    weight=0.6 * factor,
                    title="Face did not match the enrolled student",
                    description=(
                        f"Verification {v.reference} ({v.trigger.replace('_', ' ')}) returned a face similarity of "
                        f"{v.face_match_score:.2f}, below the {FACE_MISMATCH_THRESHOLD:.2f} match threshold." + suffix
                    ),
                    method="biometric",
                    version=RULES_VERSION,
                    evidence={**evidence, "face_match_score": v.face_match_score},
                )
            )
        if v.pad_result == "attack_detected":
            signals.append(
                Signal(
                    code="PRESENTATION_ATTACK",
                    category=SignalCategory.BIOMETRIC,
                    severity=Severity.CRITICAL,
                    weight=0.5 * factor,
                    title="Presentation attack detected",
                    description=(
                        f"Liveness checks flagged a {(v.pad_attack_type or 'spoofing').replace('_', ' ')} "
                        f"attempt during "
                        f"{v.reference}." + suffix
                    ),
                    method="biometric",
                    version=RULES_VERSION,
                    evidence={**evidence, "attack_type": v.pad_attack_type},
                )
            )
        if v.document_result == "suspicious":
            signals.append(
                Signal(
                    code="DOCUMENT_SUSPICIOUS",
                    category=SignalCategory.BIOMETRIC,
                    severity=Severity.HIGH,
                    weight=0.35 * factor,
                    title="Identity document failed authenticity checks",
                    description=f"The document presented in {v.reference} showed signs of tampering." + suffix,
                    method="biometric",
                    version=RULES_VERSION,
                    evidence=evidence,
                )
            )
    return signals
