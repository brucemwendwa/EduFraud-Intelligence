"""Identity verification workflows: biometric step-up (via a provider) and officer-recorded alternatives.

Outcomes feed straight back into risk scoring. A failed verification never denies aid
by itself: it raises or upgrades an alert and recommends what a person should do next.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Literal

from fastapi import Request
from sqlalchemy.orm import Session

from app.biometrics.provider import ConsentRequiredError, ProviderResult, VerificationRequest
from app.biometrics.simulated import FACE_MATCH_THRESHOLD, FACE_MISMATCH_THRESHOLD, LIVENESS_THRESHOLD, get_provider
from app.db.types import utcnow
from app.detection.engine import DetectionEngine
from app.models import FinancialAidApplication, IdentityVerification, Student, User
from app.models.enums import AuditCategory, AuditOutcome, VerificationMethod, VerificationOutcome, VerificationStatus
from app.services import audit
from app.services.references import next_reference

TRIGGER_ACTIONS = {
    "payment_destination_change": "Do not apply the requested payment-destination change.",
    "account_recovery": "Do not complete the account recovery request.",
    "new_device_login": "Sign the session out and require the student to re-authenticate.",
}


def decide(result: ProviderResult) -> tuple[VerificationOutcome, list[str]]:
    indicators: list[str] = []
    face = result.face_match_score or 0.0
    if result.document_result == "suspicious":
        indicators.append("Identity document shows signs of tampering")
    if result.document_result == "unreadable":
        indicators.append("Document could not be read (image quality)")
    if face < FACE_MISMATCH_THRESHOLD:
        indicators.append(f"Face does not match the enrolled student (similarity {face:.2f})")
    elif face < FACE_MATCH_THRESHOLD:
        indicators.append(f"Face similarity inconclusive ({face:.2f})")
    if result.liveness_result == "not_live":
        indicators.append(f"Liveness check failed (confidence {result.liveness_score or 0:.2f} < {LIVENESS_THRESHOLD})")
    if result.pad_result == "attack_detected":
        indicators.append(f"Presentation attack detected: {(result.pad_attack_type or 'spoof').replace('_', ' ')}")

    if (
        result.document_result == "suspicious"
        or face < FACE_MISMATCH_THRESHOLD
        or result.pad_result == "attack_detected"
        or result.liveness_result == "not_live"
    ):
        return VerificationOutcome.FAILED, indicators
    if result.document_result == "authentic" and face >= FACE_MATCH_THRESHOLD and result.liveness_result == "live":
        return VerificationOutcome.PASSED, indicators
    return VerificationOutcome.REVIEW, indicators


def recommend(outcome: VerificationOutcome, trigger: str, indicators: list[str]) -> str:
    if outcome == VerificationOutcome.PASSED:
        return "Identity confirmed. Proceed with the requested action."
    if outcome == VerificationOutcome.REVIEW:
        return "Inconclusive. Ask the student to retry with better lighting, or use an alternative verification method."
    first = TRIGGER_ACTIONS.get(trigger, "Do not act on this request.")
    return (
        f"{first} Hold pending refunds and contact the student through a known-good channel "
        "for in-person or officer-assisted verification. Escalate to an investigator."
    )


def _apply(
    db: Session,
    app: FinancialAidApplication,
    verification: IdentityVerification,
    *,
    user: User | None,
    request: Request | None,
    action: str,
    at: datetime,
) -> IdentityVerification:
    status_map = {
        VerificationOutcome.PASSED: VerificationStatus.PASSED,
        VerificationOutcome.FAILED: VerificationStatus.FAILED,
        VerificationOutcome.REVIEW: VerificationStatus.MANUAL_REVIEW,
    }
    app.verification_status = status_map[VerificationOutcome(verification.status)]
    db.add(verification)
    db.flush()
    audit.record(
        db,
        category=AuditCategory.VERIFICATION,
        action=action,
        outcome=AuditOutcome.SUCCESS if verification.status == VerificationOutcome.PASSED else AuditOutcome.FAILURE,
        actor=user,
        organization_id=app.organization_id,
        target_type="verification",
        target_id=verification.id,
        target_ref=verification.reference,
        details={
            "application": app.reference,
            "trigger": verification.trigger,
            "method": verification.method,
            "status": verification.status,
            "provider_mode": verification.provider_mode,
            "face_match_score": verification.face_match_score,
            "pad_result": verification.pad_result,
        },
        request=request,
    )
    # Feed the outcome back into risk scoring (and alerts) immediately.
    DetectionEngine(db, now=max(at, utcnow())).prepare().assess(app, triggered_by="verification", user=user, at=at)
    return verification


def run_biometric(
    db: Session,
    *,
    app: FinancialAidApplication,
    trigger: str,
    sample_key: str,
    user: User | None,
    request: Request | None = None,
    at: datetime | None = None,
) -> IdentityVerification:
    student: Student = app.student
    if not student.biometric_consent or not student.biometric_reference_id:
        raise ConsentRequiredError
    at = at or utcnow()
    provider = get_provider()
    result = provider.verify(
        VerificationRequest(
            biometric_reference_id=student.biometric_reference_id,
            sample_handle=sample_key,
            student_ref=student.student_ref,
            trigger=trigger,
        )
    )
    outcome, indicators = decide(result)
    verification = IdentityVerification(
        organization_id=app.organization_id,
        student_id=student.id,
        application_id=app.id,
        reference=next_reference(db, IdentityVerification, "IDV", 6),
        trigger=trigger,
        method=VerificationMethod.DOCUMENT_BIOMETRIC,
        provider=result.provider,
        provider_mode=result.mode,
        status=outcome,
        document_result=result.document_result,
        document_type=result.document_type,
        face_match_score=result.face_match_score,
        liveness_score=result.liveness_score,
        liveness_result=result.liveness_result,
        pad_result=result.pad_result,
        pad_attack_type=result.pad_attack_type,
        quality_flags=result.quality_flags,
        risk_indicators=indicators,
        recommended_action=recommend(outcome, trigger, indicators),
        sample_key=sample_key,
        session_context={"stages": [asdict(s) for s in result.stages], "channel": "student_portal_step_up"},
        initiated_by_id=user.id if user else None,
        completed_at=at,
        created_at=at,
    )
    return _apply(db, app, verification, user=user, request=request, action="verification.biometric", at=at)


def record_alternative(
    db: Session,
    *,
    app: FinancialAidApplication,
    method: Literal["in_person_id_check", "officer_video_call", "mailed_code"],
    outcome: Literal["passed", "failed"],
    trigger: str,
    notes: str,
    user: User,
    request: Request | None = None,
) -> IdentityVerification:
    at = utcnow()
    passed = outcome == "passed"
    verification = IdentityVerification(
        organization_id=app.organization_id,
        student_id=app.student_id,
        application_id=app.id,
        reference=next_reference(db, IdentityVerification, "IDV", 6),
        trigger=trigger,
        method=method,
        provider="manual",
        provider_mode="manual",
        status=VerificationOutcome.PASSED if passed else VerificationOutcome.FAILED,
        document_result="authentic" if passed else "suspicious",
        document_type="government_photo_id" if method == "in_person_id_check" else None,
        face_match_score=None,
        liveness_score=None,
        liveness_result="not_performed",
        pad_result="not_performed",
        pad_attack_type=None,
        quality_flags=[],
        risk_indicators=[] if passed else ["Officer could not confirm the student's identity"],
        recommended_action=(
            "Identity confirmed by a staff member. Proceed."
            if passed
            else "Identity not confirmed by staff. Keep funds on hold and escalate to an investigator."
        ),
        notes=notes,
        session_context={"recorded_by": user.full_name},
        initiated_by_id=user.id,
        completed_at=at,
        created_at=at,
    )
    return _apply(db, app, verification, user=user, request=request, action="verification.alternative", at=at)
