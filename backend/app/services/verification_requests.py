"""Identity re-verification requests: from trigger to a documented human decision.

Pathways
  on campus — the student is asked to visit the designated verification office, where an
              officer checks approved identity documents and records the result;
  remote    — international or remote students: secure video with an officer, approved
              government-ID document check, provider liveness check (consent required; simulated
              in this prototype), other alternative methods, or embassy/consulate-assisted
              verification *only* where the institution has a formal arrangement on file.

Every step lands on the request's timeline and in the audit trail. Only a person records the
outcome; a verified outcome can restore restricted access.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import (
    Alert,
    FinancialAidApplication,
    InvestigationCase,
    Organization,
    StudentFinancialAccount,
    StudentIDCard,
    User,
    VerificationRequest,
    VerificationRequestEvent,
)
from app.models.enums import (
    AccountStatus,
    AlertStatus,
    AuditCategory,
    CaseStatus,
    StudyMode,
    VerificationPathway,
    VerificationRequestMethod,
    VerificationRequestStatus,
)
from app.services import audit, notifications
from app.services.references import next_reference

_M = VerificationRequestMethod
_S = VerificationRequestStatus
METHODS = {
    VerificationPathway.ON_CAMPUS: (_M.IN_PERSON_ID_CHECK,),
    VerificationPathway.REMOTE: (
        _M.SECURE_VIDEO,
        _M.GOVERNMENT_ID_DOCUMENT,
        _M.LIVENESS_PROVIDER,
        _M.ALTERNATIVE_METHOD,
        _M.EMBASSY_ASSISTED,
    ),
}
METHOD_LABELS = {
    _M.IN_PERSON_ID_CHECK: "In-person ID check at the verification office",
    _M.SECURE_VIDEO: "Secure video verification with an officer",
    _M.GOVERNMENT_ID_DOCUMENT: "Approved government-issued ID document check",
    _M.LIVENESS_PROVIDER: "Liveness check via approved provider (simulated in this prototype; consent required)",
    _M.ALTERNATIVE_METHOD: "Alternative method (e.g. mailed code to the address on file, known-good callback)",
    _M.EMBASSY_ASSISTED: "Embassy/consulate-assisted verification (formal arrangement required)",
}
# Designated verification offices (fictional).
OFFICES = {
    "northbridge": "Student Financial Services, Hayes Hall 110 (Mon–Fri 9:00–16:30)",
    "lakeshore": "Financial Aid Office, Main Campus Building A, Room 204",
    "pinecrest": "Student Services Center, Technology Commons 1st floor",
}
# Formal embassy/consulate arrangements on file, by institution slug and student home country.
# Deliberately sparse: embassy assistance is unavailable unless an arrangement exists.
EMBASSY_ARRANGEMENTS: dict[str, dict[str, str]] = {
    "northbridge": {"IN": "Demonstration arrangement with a partner consulate (fictional; synthetic data)"},
}
CHECK_STEPS = (
    "documents_checked",
    "identity_procedure_completed",
    "video_session_completed",
    "alternative_method_completed",
    "embassy_confirmation_received",
)
OPEN_STATUSES = (_S.PENDING, _S.IN_PROGRESS, _S.ADDITIONAL_INFO_REQUIRED, _S.ESCALATED)


def pathway_for(account: StudentFinancialAccount | None) -> VerificationPathway:
    if account is None or account.study_mode == StudyMode.ON_CAMPUS:
        return VerificationPathway.ON_CAMPUS
    return VerificationPathway.REMOTE


def embassy_arrangement(db: Session, req: VerificationRequest, account: StudentFinancialAccount | None) -> str | None:
    org = db.get(Organization, req.organization_id)
    if org is None or account is None:
        return None
    return EMBASSY_ARRANGEMENTS.get(org.slug, {}).get(account.home_country)


def _actor_label(actor: User | None) -> str:
    return f"{actor.full_name} ({actor.role.name})" if actor else "EduShield (automatic)"


def _step(
    db: Session,
    req: VerificationRequest,
    step: str,
    *,
    actor: User | None,
    note: str | None = None,
    at: datetime | None = None,
    request: Request | None = None,
    **details: object,
) -> None:
    db.add(
        VerificationRequestEvent(
            organization_id=req.organization_id,
            request_id=req.id,
            step=step,
            status_after=req.status,
            actor_id=actor.id if actor else None,
            actor_label=_actor_label(actor),
            note=note,
            details={k: v for k, v in details.items() if v is not None},
            created_at=at or utcnow(),
        )
    )
    audit.record(
        db,
        category=AuditCategory.VERIFICATION,
        action=f"verification_request.{step}",
        actor=actor,
        actor_email=None if actor else "system:account-risk-engine",
        organization_id=req.organization_id,
        target_type="verification_request",
        target_id=req.id,
        target_ref=req.reference,
        details={"status": req.status, "note": note, **details},
        request=request,
    )
    db.flush()


def create(
    db: Session,
    *,
    account: StudentFinancialAccount,
    trigger: str,
    reason: str,
    actor: User | None,
    alert: Alert | None = None,
    case: InvestigationCase | None = None,
    card: StudentIDCard | None = None,
    at: datetime | None = None,
    request: Request | None = None,
) -> VerificationRequest:
    """Opens a request (or links to the student's open one) and notifies the student."""
    at = at or utcnow()
    existing = db.scalar(
        select(VerificationRequest).where(
            VerificationRequest.student_id == account.student_id, VerificationRequest.status.in_(OPEN_STATUSES)
        )
    )
    if existing is not None:
        existing.alert_id = existing.alert_id or (alert.id if alert else None)
        existing.case_id = existing.case_id or (case.id if case else None)
        existing.card_id = existing.card_id or (card.id if card else None)
        _link_side_effects(alert, case)
        _step(
            db,
            existing,
            "linked",
            actor=actor,
            at=at,
            request=request,
            note=reason[:300],
            alert=alert.reference if alert else None,
            case=case.reference if case else None,
        )
        return existing
    pathway = pathway_for(account)
    org = db.get(Organization, account.organization_id)
    req = VerificationRequest(
        organization_id=account.organization_id,
        student_id=account.student_id,
        account_id=account.id,
        card_id=card.id if card else None,
        alert_id=alert.id if alert else None,
        case_id=case.id if case else None,
        reference=next_reference(db, VerificationRequest, "VRQ", 5),
        trigger=trigger,
        reason=reason[:500],
        pathway=pathway,
        status=_S.PENDING,
        requested_by_id=actor.id if actor else None,
        due_at=at + timedelta(days=7 if pathway == VerificationPathway.ON_CAMPUS else 10),
        location_note=OFFICES.get(org.slug) if org and pathway == VerificationPathway.ON_CAMPUS else None,
        created_at=at,
        updated_at=at,
    )
    db.add(req)
    db.flush()
    _link_side_effects(alert, case)
    if account.status == AccountStatus.ACTIVE and not account.sensitive_actions_restricted:
        account.status, account.status_reason, account.status_changed_at = (
            AccountStatus.PENDING_VERIFICATION,
            f"Identity re-verification requested ({req.reference})",
            at,
        )
    _step(db, req, "created", actor=actor, at=at, request=request, note=reason[:300], trigger=trigger, pathway=pathway)
    notify_student(db, req, actor=actor, at=at + timedelta(microseconds=1), request=request)
    notifications.notify_permission_holders(
        db,
        organization_id=req.organization_id,
        permission=P.VERIFICATIONS_DECIDE,
        kind="verification",
        title=f"Verification request {req.reference}",
        body=f"{pathway.replace('_', ' ').capitalize()} identity verification needed for {account.reference}.",
        link=f"/app/verification?tab=requests&selected={req.id}",
    )
    return req


def _link_side_effects(alert: Alert | None, case: InvestigationCase | None) -> None:
    if alert is not None and alert.status in (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED, AlertStatus.ESCALATED):
        alert.status = AlertStatus.VERIFICATION_REQUESTED
    if case is not None and case.status in (CaseStatus.NEW, CaseStatus.UNDER_REVIEW):
        case.status = CaseStatus.AWAITING_VERIFICATION


def notify_student(
    db: Session,
    req: VerificationRequest,
    *,
    actor: User | None,
    at: datetime | None = None,
    request: Request | None = None,
) -> None:
    """Simulated notification through the student's verified contact channel (no message is sent)."""
    at = at or utcnow()
    req.notified_at = at
    channel = "student portal + email on file (simulated delivery)"
    note = (
        f"Asked to visit {req.location_note} with approved photo ID."
        if req.pathway == VerificationPathway.ON_CAMPUS
        else "Asked to choose a remote verification method."
    )
    _step(db, req, "student_notified", actor=actor, at=at, request=request, note=note, channel=channel)


def _require_open(req: VerificationRequest) -> None:
    if req.status not in OPEN_STATUSES:
        raise ConflictError(f"Verification request {req.reference} is already {req.status.replace('_', ' ')}.")


def schedule(
    db: Session,
    req: VerificationRequest,
    *,
    appointment_at: datetime,
    location_note: str | None,
    actor: User,
    request: Request | None = None,
) -> None:
    _require_open(req)
    if req.pathway != VerificationPathway.ON_CAMPUS:
        raise ConflictError("Appointments apply to on-campus verification; start a remote method instead.")
    req.appointment_at, req.method = appointment_at, _M.IN_PERSON_ID_CHECK
    req.location_note = location_note or req.location_note
    req.status, req.assigned_to_id = _S.IN_PROGRESS, req.assigned_to_id or actor.id
    _step(
        db,
        req,
        "appointment_scheduled",
        actor=actor,
        request=request,
        note=f"Visit booked for {appointment_at:%d %b %Y %H:%M} UTC at {req.location_note}.",
    )


def start(
    db: Session,
    req: VerificationRequest,
    *,
    method: VerificationRequestMethod,
    note: str | None,
    actor: User,
    account: StudentFinancialAccount | None,
    request: Request | None = None,
) -> None:
    _require_open(req)
    if method == _M.EMBASSY_ASSISTED and embassy_arrangement(db, req, account) is None:
        raise ConflictError(
            "No formal embassy or consulate arrangement is on file for this student's country. Choose another method."
        )
    if method == _M.LIVENESS_PROVIDER and not req.student.biometric_consent:
        raise ConflictError("The student has not consented to biometric checks. Use secure video or a document check.")
    if method not in METHODS[req.pathway]:
        previous = req.pathway
        req.pathway = VerificationPathway.ON_CAMPUS if method == _M.IN_PERSON_ID_CHECK else VerificationPathway.REMOTE
        _step(
            db, req, "pathway_changed", actor=actor, request=request, note=note, **{"from": previous, "to": req.pathway}
        )
    req.method, req.status, req.assigned_to_id = method, _S.IN_PROGRESS, req.assigned_to_id or actor.id
    _step(db, req, "session_started", actor=actor, request=request, note=note or METHOD_LABELS[method], method=method)


def record_check(
    db: Session,
    req: VerificationRequest,
    *,
    step: str,
    result: str,
    note: str,
    actor: User,
    request: Request | None = None,
) -> None:
    _require_open(req)
    if step not in CHECK_STEPS:
        raise ValidationFailedError(f"Unknown verification step '{step}'.")
    if req.status == _S.PENDING:
        raise ConflictError("Schedule the visit or start a remote method before recording checks.")
    _step(db, req, step, actor=actor, request=request, note=note, result=result)


def run_liveness(
    db: Session, req: VerificationRequest, *, sample_key: str, actor: User, request: Request | None = None
) -> None:
    """Runs the provider liveness/document/face pipeline (SimulatedBiometricProvider in this prototype)."""
    from app.services.verification import run_biometric

    _require_open(req)
    if req.method != _M.LIVENESS_PROVIDER:
        raise ConflictError("Start the 'liveness via approved provider' method first.")
    app = db.scalar(
        select(FinancialAidApplication)
        .where(FinancialAidApplication.student_id == req.student_id)
        .order_by(FinancialAidApplication.submitted_at.desc())
    )
    if app is None:
        raise ConflictError("No aid record is linked to this student for the provider check.")
    attempt = run_biometric(db, app=app, trigger="account_recovery", sample_key=sample_key, user=actor, request=request)
    req.identity_verification_id = attempt.id
    _step(
        db,
        req,
        "liveness_check_completed",
        actor=actor,
        request=request,
        note=f"SIMULATION — {attempt.recommended_action}",
        result=attempt.status,
        attempt=attempt.reference,
        provider_mode=attempt.provider_mode,
    )


def decide(
    db: Session,
    req: VerificationRequest,
    *,
    outcome: VerificationRequestStatus,
    reason: str,
    restore_access: bool,
    actor: User,
    request: Request | None = None,
) -> None:
    from app.services import accounts

    _require_open(req)
    if outcome == _S.VERIFIED and req.status == _S.PENDING:
        raise ConflictError("Record at least one verification step before confirming identity.")
    now = utcnow()
    req.status, req.outcome_reason = outcome, reason
    if outcome in (_S.VERIFIED, _S.FAILED):
        req.decided_by_id, req.decided_at = actor.id, now
    account = db.get(StudentFinancialAccount, req.account_id) if req.account_id else None
    alert = db.get(Alert, req.alert_id) if req.alert_id else None
    case = db.get(InvestigationCase, req.case_id) if req.case_id else None
    _step(db, req, f"decision_{outcome}", actor=actor, request=request, note=reason, restore_access=restore_access)

    if outcome == _S.VERIFIED:
        if alert is not None and alert.status == AlertStatus.VERIFICATION_REQUESTED:
            alert.status = AlertStatus.ACKNOWLEDGED
            alert.triage_note = f"Identity verified via {req.reference}; awaiting reviewer decision."
        if case is not None and case.status == CaseStatus.AWAITING_VERIFICATION:
            case.status = CaseStatus.UNDER_REVIEW
        if account is not None and restore_access:
            if account.sensitive_actions_restricted:
                accounts.lift_restriction(
                    db,
                    account,
                    reason=f"Identity verified ({req.reference}): {reason}"[:300],
                    actor=actor,
                    request=request,
                )
            if account.status == AccountStatus.PENDING_VERIFICATION:
                account.status, account.status_reason, account.status_changed_at = (
                    AccountStatus.ACTIVE,
                    f"Identity verified ({req.reference})",
                    now,
                )
            req.access_restored = True
            _step(db, req, "access_restored", actor=actor, request=request)
    elif outcome in (_S.FAILED, _S.ESCALATED):
        if alert is not None and alert.status in (AlertStatus.VERIFICATION_REQUESTED, AlertStatus.ACKNOWLEDGED):
            alert.status = AlertStatus.ESCALATED
        if case is not None and case.status == CaseStatus.AWAITING_VERIFICATION:
            case.status = CaseStatus.UNDER_REVIEW
    elif outcome == _S.ADDITIONAL_INFO_REQUIRED:
        notify_student(db, req, actor=actor, request=request)
    if account is not None:
        accounts.reassess(db, account, triggered_by="verification", user=actor)
