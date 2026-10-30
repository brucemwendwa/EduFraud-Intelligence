"""API views for assessments and alerts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    AlertNote,
    AuditEvent,
    Disbursement,
    FinancialAidApplication,
    IdentityVerification,
    InvestigationCase,
    RiskAssessment,
    SecurityEvent,
    Student,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    User,
    VerificationRequest,
)
from app.schemas.common import OrgRef, UserRef
from app.schemas.risk import (
    AlertDetail,
    AlertNoteOut,
    AlertRow,
    AlertTimelineItem,
    AssessmentHistoryItem,
    RelatedRecord,
    RiskAssessmentOut,
)
from app.services import records


def current_assessment(db: Session, application_id: uuid.UUID) -> RiskAssessmentOut | None:
    a = db.scalar(
        select(RiskAssessment).where(RiskAssessment.application_id == application_id, RiskAssessment.is_current)
    )
    return RiskAssessmentOut.model_validate(a) if a else None


def assessment_history(db: Session, application_id: uuid.UUID, limit: int = 20) -> list[AssessmentHistoryItem]:
    rows = db.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.application_id == application_id)
        .order_by(RiskAssessment.created_at.desc())
        .limit(limit)
    ).all()
    return [AssessmentHistoryItem.model_validate(r) for r in rows]


def _refs(db: Session, model: type, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(model.id, model.reference).where(model.id.in_(ids))).all())  # type: ignore[attr-defined]


def alert_rows(db: Session, alerts: list[Alert]) -> list[AlertRow]:
    orgs = records.org_map(db)
    apps = _refs(db, FinancialAidApplication, {a.application_id for a in alerts})  # type: ignore[arg-type]
    cases = _refs(db, InvestigationCase, {a.case_id for a in alerts})  # type: ignore[arg-type]
    accounts = _refs(db, StudentFinancialAccount, {a.account_id for a in alerts})  # type: ignore[arg-type]
    student_ids = {a.student_id for a in alerts if a.student_id}
    students = (
        dict(db.execute(select(Student.id, Student.student_ref).where(Student.id.in_(student_ids))).all())
        if student_ids
        else {}
    )
    assignee_ids = {a.assigned_to_id for a in alerts if a.assigned_to_id}
    assignees = {u.id: u for u in db.scalars(select(User).where(User.id.in_(assignee_ids)))} if assignee_ids else {}
    return [
        AlertRow(
            id=a.id,
            reference=a.reference,
            organization=OrgRef.model_validate(orgs[a.organization_id]),
            category=a.category,
            severity=a.severity,
            title=a.title,
            summary=a.summary,
            status=a.status,
            risk_score=a.risk_score,
            application_id=a.application_id,
            application_ref=apps.get(a.application_id),  # type: ignore[arg-type]
            account_id=a.account_id,
            account_ref=accounts.get(a.account_id),  # type: ignore[arg-type]
            student_ref=students.get(a.student_id),  # type: ignore[arg-type]
            case_id=a.case_id,
            case_ref=cases.get(a.case_id),  # type: ignore[arg-type]
            assigned_to=UserRef.model_validate(assignees[a.assigned_to_id]) if a.assigned_to_id in assignees else None,
            recommended_action=a.recommended_action,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in alerts
    ]


def _related(db: Session, alert: Alert) -> list[RelatedRecord]:
    out: list[RelatedRecord] = []
    if alert.account_id and (acct := db.get(StudentFinancialAccount, alert.account_id)):
        out.append(
            RelatedRecord(
                kind="account",
                id=acct.id,
                reference=acct.reference,
                label="Financial aid account",
                status=acct.status,
                link=f"/app/accounts/{acct.id}",
            )
        )
    if alert.card_id and (card := db.get(StudentIDCard, alert.card_id)):
        out.append(
            RelatedRecord(
                kind="card",
                id=card.id,
                reference=card.reference,
                label=f"Student ID card •••• {card.display_suffix}",
                status=card.status,
                link=f"/app/cards?selected={card.id}",
            )
        )
    if alert.transaction_id and (txn := db.get(Transaction, alert.transaction_id)):
        out.append(
            RelatedRecord(
                kind="transaction",
                id=txn.id,
                reference=txn.reference,
                label=f"{txn.merchant_category.replace('_', ' ')} · ${txn.amount:,.2f}",
                status=txn.status,
                link=f"/app/transactions?selected={txn.id}",
            )
        )
    if alert.security_event_id and (ev := db.get(SecurityEvent, alert.security_event_id)):
        out.append(
            RelatedRecord(
                kind="security_event",
                id=ev.id,
                reference=ev.reference,
                label=ev.event_type.replace("_", " ").capitalize(),
                status=ev.outcome,
                link=f"/app/access?selected={ev.id}",
            )
        )
    reqs = db.scalars(
        select(VerificationRequest).where(
            (VerificationRequest.alert_id == alert.id)
            | ((VerificationRequest.student_id == alert.student_id) & VerificationRequest.student_id.is_not(None))
        )
    ).all()
    for r in reqs:
        out.append(
            RelatedRecord(
                kind="verification_request",
                id=r.id,
                reference=r.reference,
                label=f"{r.pathway.replace('_', ' ')} verification",
                status=r.status,
                link=f"/app/verification?tab=requests&selected={r.id}",
            )
        )
    return out


def alert_timeline(db: Session, alert: Alert) -> list[AlertTimelineItem]:
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.target_type == "alert", AuditEvent.target_id == str(alert.id))
        .order_by(AuditEvent.sequence)
    ).all()
    items = [
        AlertTimelineItem(
            action="alert.raised",
            actor="EduShield detection",
            outcome="success",
            details={"severity": alert.severity, "score": alert.risk_score},
            occurred_at=alert.created_at,
        )
    ]
    items += [
        AlertTimelineItem(
            action=e.action, actor=e.actor_email, outcome=e.outcome, details=e.details, occurred_at=e.occurred_at
        )
        for e in events
    ]
    return items


def alert_detail(db: Session, alert: Alert) -> AlertDetail:
    row = alert_rows(db, [alert])[0]
    app = db.get(FinancialAidApplication, alert.application_id) if alert.application_id else None
    assessment = db.get(RiskAssessment, alert.assessment_id) if alert.assessment_id else None
    triager = db.get(User, alert.triaged_by_id) if alert.triaged_by_id else None
    student = app.student if app else (db.get(Student, alert.student_id) if alert.student_id else None)
    notes = db.scalars(select(AlertNote).where(AlertNote.alert_id == alert.id).order_by(AlertNote.created_at)).all()
    authors = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({n.author_id for n in notes})))}
    return AlertDetail(
        **row.model_dump(),
        student=records.student_ref(student) if student else None,
        assessment=RiskAssessmentOut.model_validate(assessment) if assessment else None,
        disbursement_id=alert.disbursement_id,
        disbursement_ref=_refs(db, Disbursement, {alert.disbursement_id}).get(alert.disbursement_id),  # type: ignore[arg-type]
        verification_id=alert.verification_id,
        verification_ref=_refs(db, IdentityVerification, {alert.verification_id}).get(alert.verification_id),  # type: ignore[arg-type]
        triage_note=alert.triage_note,
        triaged_by=triager.full_name if triager else None,
        triaged_at=alert.triaged_at,
        related=_related(db, alert),
        notes=[
            AlertNoteOut(id=n.id, body=n.body, author=authors.get(n.author_id), created_at=n.created_at)  # type: ignore[arg-type]
            for n in notes
        ],
        timeline=alert_timeline(db, alert),
    )
