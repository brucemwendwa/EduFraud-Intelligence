"""Investigation case workflow: human-led decisions over AI-raised suspicions.

Principles enforced here:
  * The AI only ever raises *suspicious activity* (alerts). Findings change only through a recorded
    human decision with a written justification, the deciding investigator and a timestamp.
  * Suspicion, suspected fraud and confirmed findings stay distinct (`CaseFinding`), and a case can be
    resolved without labelling anyone fraudulent (no fraud found, insufficient evidence, referral).
  * Confirming fraud demands supporting evidence on the case and a fuller justification.
  * Evidence that references a record is snapshotted server-side from that record, after checking it
    belongs to the case's institution, so the evidence trail cannot be fabricated or leak across tenants.
  * Every consequential action is written to the hash-chained audit trail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import (
    Alert,
    AuditEvent,
    CaseDecision,
    CaseEvidence,
    CaseNote,
    Disbursement,
    FinancialAidApplication,
    IdentityVerification,
    InvestigationCase,
    RiskAssessment,
    User,
)
from app.models.enums import (
    AlertStatus,
    AuditCategory,
    CaseDecisionType,
    CaseFinding,
    CasePriority,
    CaseResolution,
    CaseStatus,
    ReviewStatus,
)
from app.services import audit, notifications
from app.services.references import next_reference

OPEN_STATUSES = (CaseStatus.NEW, CaseStatus.UNDER_REVIEW, CaseStatus.ESCALATED)
LIVE_ALERTS = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)
PRIORITY_BY_LEVEL = {
    "critical": CasePriority.URGENT,
    "high": CasePriority.HIGH,
    "medium": CasePriority.MEDIUM,
    "low": CasePriority.LOW,
}
SLA_DAYS = {CasePriority.URGENT: 2, CasePriority.HIGH: 5, CasePriority.MEDIUM: 10, CasePriority.LOW: 20}
MIN_JUSTIFICATION = 20
MIN_CONFIRMED_JUSTIFICATION = 50

# Which decisions are allowed from which status, and where they lead.
TRANSITIONS: dict[CaseDecisionType, tuple[tuple[str, ...], CaseStatus]] = {
    CaseDecisionType.ESCALATE: ((CaseStatus.NEW, CaseStatus.UNDER_REVIEW), CaseStatus.ESCALATED),
    CaseDecisionType.RESOLVE: (OPEN_STATUSES, CaseStatus.RESOLVED),
    CaseDecisionType.REOPEN: ((CaseStatus.RESOLVED,), CaseStatus.UNDER_REVIEW),
    CaseDecisionType.CLOSE: ((CaseStatus.RESOLVED,), CaseStatus.CLOSED),
}
FINDING_BY_OUTCOME = {
    CaseResolution.CONFIRMED_FRAUD: CaseFinding.CONFIRMED_FRAUD,
    CaseResolution.REFERRED_EXTERNALLY: CaseFinding.SUSPECTED_FRAUD,
    CaseResolution.NO_FRAUD_FOUND: CaseFinding.NOT_SUBSTANTIATED,
    CaseResolution.INSUFFICIENT_EVIDENCE: CaseFinding.NOT_SUBSTANTIATED,
}


def record_event(
    db: Session, case: InvestigationCase, actor: User, action: str, request: Request | None, **details: Any
) -> None:
    audit.record(
        db,
        category=AuditCategory.INVESTIGATION,
        action=action,
        actor=actor,
        organization_id=case.organization_id,
        target_type="case",
        target_id=case.id,
        target_ref=case.reference,
        details={k: v for k, v in details.items() if v is not None},
        request=request,
    )


def ensure_open(case: InvestigationCase, action: str) -> None:
    if case.status == CaseStatus.CLOSED:
        raise ConflictError(f"Case {case.reference} is closed; reopen is not possible, so you cannot {action}.")


def resolve_assignee(db: Session, org_id: uuid.UUID, user_id: uuid.UUID | None) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or user.organization_id != org_id:
        raise NotFoundError("Assignee not found.")
    if not user.is_active or P.CASES_UPDATE.value not in user.permission_keys:
        raise ConflictError("Assignee must be an active investigator with case-update access.")
    return user


# --------------------------------------------------------------------------- evidence snapshots
def snapshot_evidence(db: Session, org_id: uuid.UUID, evidence_type: str, ref_id: uuid.UUID) -> dict[str, Any]:
    """Builds title, summary and data from the referenced record (which must belong to the institution)."""

    def scoped(model: type, label: str):  # type: ignore[no-untyped-def]
        obj = db.get(model, ref_id)
        if obj is None or obj.organization_id != org_id:
            raise NotFoundError(f"{label} not found.")
        return obj

    if evidence_type == "alert":
        a: Alert = scoped(Alert, "Alert")
        return {
            "ref_label": a.reference,
            "title": f"Alert {a.reference}: {a.title}",
            "summary": a.summary,
            "data": {
                "severity": a.severity,
                "category": a.category,
                "risk_score": a.risk_score,
                "raised": a.created_at.isoformat(),
            },
        }
    if evidence_type == "risk_assessment":
        r: RiskAssessment = scoped(RiskAssessment, "Risk assessment")
        return {
            "ref_label": f"{r.level.upper()} {r.score:.0f}",
            "title": f"Risk assessment: {r.score:.0f}/100 ({r.level})",
            "summary": r.explanation,
            "data": {
                "rules_version": r.rules_version,
                "model_version": r.model_version,
                "assessed": r.created_at.isoformat(),
                "signals": [{"code": s.code, "title": s.title, "points": s.points} for s in r.signals],
            },
        }
    if evidence_type == "verification":
        v: IdentityVerification = scoped(IdentityVerification, "Verification")
        return {
            "ref_label": v.reference,
            "title": f"Identity verification {v.reference}: {v.status}",
            "summary": "; ".join(v.risk_indicators or []) or v.recommended_action,
            "data": {
                "trigger": v.trigger,
                "method": v.method,
                "provider_mode": v.provider_mode,
                "face_match_score": v.face_match_score,
                "pad_result": v.pad_result,
                "completed": v.completed_at.isoformat() if v.completed_at else None,
            },
        }
    if evidence_type == "disbursement":
        d: Disbursement = scoped(Disbursement, "Disbursement")
        return {
            "ref_label": d.reference,
            "title": f"Disbursement {d.reference}: ${float(d.amount):,.2f} {d.fund_type.replace('_', ' ')}",
            "summary": "; ".join(d.risk_flags or []) or "No risk indicators on this disbursement.",
            "data": {"status": d.status, "risk_score": d.risk_score, "disbursed": d.disbursed_at.isoformat()},
        }
    if evidence_type == "application":
        app: FinancialAidApplication = scoped(FinancialAidApplication, "Application")
        return {
            "ref_label": app.reference,
            "title": f"Application {app.reference}",
            "summary": f"{app.program}; status {app.status}; risk {app.risk_score or 0:.0f} ({app.risk_level}).",
            "data": {"award_year": app.award_year, "submitted": app.submitted_at.isoformat()},
        }
    raise ValidationFailedError("This evidence type cannot reference a record.")


def add_evidence(
    db: Session,
    case: InvestigationCase,
    actor: User,
    *,
    evidence_type: str,
    ref_id: uuid.UUID | None = None,
    title: str | None = None,
    summary: str | None = None,
    ref_label: str | None = None,
    data: dict[str, Any] | None = None,
    request: Request | None = None,
    automatic: bool = False,
) -> CaseEvidence:
    ensure_open(case, "add evidence")
    if ref_id is not None:
        duplicate = next((e for e in case.evidence if e.ref_id == ref_id and e.evidence_type == evidence_type), None)
        if duplicate:
            raise ConflictError("This record is already attached to the case as evidence.")
        snap = snapshot_evidence(db, case.organization_id, evidence_type, ref_id)
    else:
        if not title or not summary:
            raise ValidationFailedError(
                "A title and summary are required for evidence that does not reference a record."
            )
        snap = {"ref_label": ref_label, "title": title, "summary": summary, "data": data or {}}
    evidence = CaseEvidence(
        organization_id=case.organization_id,
        case_id=case.id,
        added_by_id=actor.id,
        evidence_type=evidence_type,
        ref_id=ref_id,
        ref_label=snap["ref_label"],
        title=(title or snap["title"]).strip()[:200],
        summary=(summary or snap["summary"]).strip(),
        data=snap["data"],
    )
    case.evidence.append(evidence)
    db.flush()
    record_event(
        db,
        case,
        actor,
        "case.evidence_add",
        request,
        evidence_type=evidence_type,
        ref=snap["ref_label"],
        automatic=True if automatic else None,
    )
    return evidence


# --------------------------------------------------------------------------- lifecycle
def open_case(
    db: Session,
    actor: User,
    *,
    app: FinancialAidApplication | None,
    alert: Alert | None,
    title: str | None,
    fraud_category: str | None,
    priority: str | None,
    assignee_id: uuid.UUID | None,
    due_at: datetime | None,
    request: Request | None = None,
) -> InvestigationCase:
    if alert and alert.case_id:
        raise ConflictError(
            "This alert is already linked to an investigation case.", details={"case_id": str(alert.case_id)}
        )
    if alert and app and alert.application_id and alert.application_id != app.id:
        raise ConflictError("The alert and application must refer to the same record.")
    if app is None and alert is not None and alert.application_id:
        app = db.get(FinancialAidApplication, alert.application_id)
    org_id = app.organization_id if app else alert.organization_id  # type: ignore[union-attr]
    if app is not None:
        existing = db.scalar(
            select(InvestigationCase).where(
                InvestigationCase.application_id == app.id, InvestigationCase.status.in_(OPEN_STATUSES)
            )
        )
        if existing:
            raise ConflictError(
                f"{existing.reference} is already open for this application.", details={"case_id": str(existing.id)}
            )

    live_alerts = (
        list(db.scalars(select(Alert).where(Alert.application_id == app.id, Alert.status.in_(LIVE_ALERTS))))
        if app
        else []
    )
    if alert and alert not in live_alerts:
        live_alerts.append(alert)
    lead = alert or (max(live_alerts, key=lambda a: a.risk_score or 0) if live_alerts else None)
    level = app.risk_level if app else alert.severity  # type: ignore[union-attr]
    chosen_priority = priority or PRIORITY_BY_LEVEL.get(level or "medium", CasePriority.MEDIUM)
    assignee = resolve_assignee(db, org_id, assignee_id)
    reference_label = app.reference if app else alert.reference  # type: ignore[union-attr]
    case = InvestigationCase(
        organization_id=org_id,
        reference=next_reference(db, InvestigationCase, "CASE", 5),
        title=(title or (f"{lead.title}: {reference_label}" if lead else f"Review of {reference_label}")).strip()[:200],
        application_id=app.id if app else None,
        fraud_category=fraud_category or (lead.category if lead else "application"),
        priority=chosen_priority,
        status=CaseStatus.NEW,
        finding=CaseFinding.SUSPICIOUS_ACTIVITY,
        risk_score_at_open=app.risk_score if app else alert.risk_score,  # type: ignore[union-attr]
        assigned_to_id=assignee.id if assignee else None,
        created_by_id=actor.id,
        due_at=due_at or utcnow() + timedelta(days=SLA_DAYS[CasePriority(chosen_priority)]),
    )
    db.add(case)
    db.flush()
    for a in live_alerts:
        a.case_id = case.id
        a.status = AlertStatus.IN_INVESTIGATION
    record_event(
        db,
        case,
        actor,
        "case.create",
        request,
        application=app.reference if app else None,
        alerts=[a.reference for a in live_alerts] or None,
        priority=chosen_priority,
        assigned_to=assignee.email if assignee else None,
    )
    _attach_initial_evidence(db, case, actor, app, live_alerts, request)
    if assignee and assignee.id != actor.id:
        _notify_assignment(db, case, assignee)
    return case


def _attach_initial_evidence(
    db: Session,
    case: InvestigationCase,
    actor: User,
    app: FinancialAidApplication | None,
    alerts: list[Alert],
    request: Request | None,
) -> None:
    """Pre-attaches the records that justified opening the case, so investigators start from the evidence."""
    for a in alerts:
        add_evidence(db, case, actor, evidence_type="alert", ref_id=a.id, request=request, automatic=True)
    if app is None:
        return
    assessment = db.scalar(
        select(RiskAssessment).where(RiskAssessment.application_id == app.id, RiskAssessment.is_current)
    )
    if assessment:
        add_evidence(
            db, case, actor, evidence_type="risk_assessment", ref_id=assessment.id, request=request, automatic=True
        )
    for v in db.scalars(
        select(IdentityVerification).where(
            IdentityVerification.application_id == app.id, IdentityVerification.status == "failed"
        )
    ):
        add_evidence(db, case, actor, evidence_type="verification", ref_id=v.id, request=request, automatic=True)
    for d in db.scalars(
        select(Disbursement).where(Disbursement.application_id == app.id, Disbursement.risk_score >= 30)
    ):
        add_evidence(db, case, actor, evidence_type="disbursement", ref_id=d.id, request=request, automatic=True)


def _notify_assignment(db: Session, case: InvestigationCase, assignee: User) -> None:
    notifications.notify_user(
        db,
        user_id=assignee.id,
        organization_id=case.organization_id,
        kind="case_assigned",
        title=f"{case.reference} assigned to you",
        body=case.title,
        link=f"/app/cases/{case.id}",
    )


def assign(
    db: Session,
    case: InvestigationCase,
    actor: User,
    assignee_id: uuid.UUID | None,
    note: str | None,
    request: Request | None,
) -> None:
    ensure_open(case, "reassign it")
    previous = case.assigned_to
    assignee = resolve_assignee(db, case.organization_id, assignee_id)
    case.assigned_to_id = assignee.id if assignee else None
    record_event(
        db,
        case,
        actor,
        "case.assign",
        request,
        assigned_to=assignee.email if assignee else "unassigned",
        previous=previous.email if previous else "unassigned",
        note=note,
    )
    if assignee and assignee.id != actor.id:
        _notify_assignment(db, case, assignee)


def start_review(db: Session, case: InvestigationCase, actor: User, request: Request | None) -> None:
    if case.status != CaseStatus.NEW:
        raise ConflictError("Only new cases can be moved to review. Use a decision for other status changes.")
    case.status = CaseStatus.UNDER_REVIEW
    if case.assigned_to_id is None:
        case.assigned_to_id = actor.id
    record_event(db, case, actor, "case.status_change", request, from_status="new", to_status="under_review")


def add_note(db: Session, case: InvestigationCase, actor: User, body: str, request: Request | None) -> CaseNote:
    ensure_open(case, "add notes")
    note = CaseNote(organization_id=case.organization_id, case_id=case.id, author_id=actor.id, body=body.strip())
    case.notes.append(note)
    db.flush()
    record_event(db, case, actor, "case.note_add", request, length=len(note.body))
    return note


def decide(
    db: Session,
    case: InvestigationCase,
    actor: User,
    *,
    decision: CaseDecisionType,
    outcome: CaseResolution | None,
    justification: str,
    request: Request | None,
) -> CaseDecision:
    """Records a human decision. The only path by which a case's finding or terminal status can change."""
    allowed_from, to_status = TRANSITIONS[decision]
    if case.status not in allowed_from:
        raise ConflictError(
            f"A case that is '{case.status.replace('_', ' ')}' cannot be {decision.value}d.",
            details={"allowed_from": list(allowed_from)},
        )
    justification = justification.strip()
    if len(justification) < MIN_JUSTIFICATION:
        raise ValidationFailedError(
            "Explain the reasoning behind this decision.",
            details=[{"field": "justification", "message": f"At least {MIN_JUSTIFICATION} characters"}],
        )

    if decision == CaseDecisionType.RESOLVE:
        if outcome is None:
            raise ValidationFailedError("Choose an outcome.", details=[{"field": "outcome", "message": "Required"}])
        if outcome == CaseResolution.CONFIRMED_FRAUD:
            if not case.evidence:
                raise ConflictError("Attach supporting evidence before recording a confirmed fraud finding.")
            if len(justification) < MIN_CONFIRMED_JUSTIFICATION:
                raise ValidationFailedError(
                    "A confirmed finding needs a fuller justification.",
                    details=[
                        {"field": "justification", "message": f"At least {MIN_CONFIRMED_JUSTIFICATION} characters"}
                    ],
                )
        finding = FINDING_BY_OUTCOME[outcome]
    elif outcome is not None:
        raise ValidationFailedError("An outcome only applies to a resolve decision.")
    elif decision == CaseDecisionType.ESCALATE:
        finding = CaseFinding.SUSPECTED_FRAUD
    elif decision == CaseDecisionType.REOPEN:
        finding = CaseFinding.SUSPICIOUS_ACTIVITY
    else:  # close keeps the finding reached at resolution
        finding = CaseFinding(case.finding)

    now = utcnow()
    record = CaseDecision(
        organization_id=case.organization_id,
        case_id=case.id,
        decision=decision,
        outcome=outcome,
        finding=finding,
        from_status=case.status,
        to_status=to_status,
        justification=justification,
        decided_by_id=actor.id,
        decided_at=now,
    )
    case.decisions.append(record)
    case.status, case.finding = to_status, finding
    if decision == CaseDecisionType.RESOLVE:
        case.resolution, case.resolution_summary, case.resolved_at = outcome, justification, now
        _apply_resolution(db, case, outcome)  # type: ignore[arg-type]
    elif decision == CaseDecisionType.REOPEN:
        case.resolution = case.resolution_summary = case.resolved_at = None
        for a in db.scalars(select(Alert).where(Alert.case_id == case.id, Alert.status == AlertStatus.RESOLVED)):
            a.status = AlertStatus.IN_INVESTIGATION
    elif decision == CaseDecisionType.CLOSE:
        case.closed_at = now
    db.flush()
    record_event(
        db,
        case,
        actor,
        f"case.decision.{decision.value}",
        request,
        outcome=outcome.value if outcome else None,
        finding=finding.value,
        from_status=record.from_status,
        to_status=to_status,
        justification=justification,
    )
    if case.created_by_id and case.created_by_id != actor.id:
        notifications.notify_user(
            db,
            user_id=case.created_by_id,
            organization_id=case.organization_id,
            kind="case_update",
            title=f"{case.reference}: {decision.value} decision recorded",
            body=f"{actor.full_name} recorded '{(outcome or decision).replace('_', ' ')}'.",
            link=f"/app/cases/{case.id}",
        )
    return record


def _apply_resolution(db: Session, case: InvestigationCase, outcome: CaseResolution) -> None:
    """Closes the linked alerts and records the review outcome on the application.

    The application's aid status is deliberately left alone: aid decisions follow the institution's
    own due-process procedures, informed by (not made by) this finding.
    """
    for a in db.scalars(select(Alert).where(Alert.case_id == case.id)):
        a.status = AlertStatus.RESOLVED
    if case.application_id:
        app = db.get(FinancialAidApplication, case.application_id)
        if app is not None:
            app.review_status = (
                ReviewStatus.CLEARED
                if outcome in (CaseResolution.NO_FRAUD_FOUND, CaseResolution.INSUFFICIENT_EVIDENCE)
                else ReviewStatus.ESCALATED
            )


# --------------------------------------------------------------------------- timeline
@dataclass
class TimelineEntry:
    at: datetime
    kind: str
    title: str
    actor: str | None
    detail: str | None


_ACTION_TITLES = {
    "case.create": "Case opened",
    "case.assign": "Assignment changed",
    "case.status_change": "Review started",
    "case.note_add": "Note added",
    "case.evidence_add": "Evidence attached",
    "case.update": "Case details updated",
    "case.decision.escalate": "Escalated: suspected fraud",
    "case.decision.resolve": "Resolved",
    "case.decision.reopen": "Reopened",
    "case.decision.close": "Closed",
}


def timeline(db: Session, case: InvestigationCase) -> list[TimelineEntry]:
    """Case history from the audit trail, plus the system events that led to the case."""
    entries: list[TimelineEntry] = []
    for e in db.scalars(
        select(AuditEvent).where(AuditEvent.target_type == "case", AuditEvent.target_id == str(case.id))
    ):
        d = e.details or {}
        detail = (
            d.get("justification")
            or (f"{d.get('ref')}" if e.action == "case.evidence_add" else None)
            or (f"{d.get('previous')} → {d.get('assigned_to')}" if e.action == "case.assign" else None)
        )
        title = _ACTION_TITLES.get(e.action, e.action)
        if e.action == "case.decision.resolve" and d.get("outcome"):
            title = f"Resolved: {d['outcome'].replace('_', ' ')}"
        if e.action == "case.evidence_add" and d.get("automatic"):
            title = "Evidence attached automatically"
        entries.append(TimelineEntry(e.occurred_at, e.action, title, e.actor_email, detail))
    if case.application_id:
        for a in db.scalars(select(Alert).where(Alert.application_id == case.application_id)):
            entries.append(
                TimelineEntry(
                    a.created_at, "alert.raised", f"Alert {a.reference} raised: {a.title}", "detection engine", None
                )
            )
        for v in db.scalars(
            select(IdentityVerification).where(
                IdentityVerification.application_id == case.application_id, IdentityVerification.status != "passed"
            )
        ):
            entries.append(
                TimelineEntry(
                    v.created_at,
                    "verification",
                    f"Verification {v.reference} {v.status}",
                    "simulated provider" if v.provider_mode == "simulation" else "staff",
                    "; ".join(v.risk_indicators or []) or None,
                )
            )
    return sorted(entries, key=lambda t: t.at)
