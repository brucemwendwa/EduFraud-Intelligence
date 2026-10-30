"""API views for assessments and alerts."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Alert,
    Disbursement,
    FinancialAidApplication,
    IdentityVerification,
    InvestigationCase,
    RiskAssessment,
    User,
)
from app.schemas.common import OrgRef
from app.schemas.risk import AlertDetail, AlertRow, AssessmentHistoryItem, RiskAssessmentOut
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
            case_id=a.case_id,
            case_ref=cases.get(a.case_id),  # type: ignore[arg-type]
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in alerts
    ]


def alert_detail(db: Session, alert: Alert) -> AlertDetail:
    row = alert_rows(db, [alert])[0]
    app = db.get(FinancialAidApplication, alert.application_id) if alert.application_id else None
    assessment = db.get(RiskAssessment, alert.assessment_id) if alert.assessment_id else None
    triager = db.get(User, alert.triaged_by_id) if alert.triaged_by_id else None
    return AlertDetail(
        **row.model_dump(),
        student=records.student_ref(app.student) if app else None,
        assessment=RiskAssessmentOut.model_validate(assessment) if assessment else None,
        disbursement_id=alert.disbursement_id,
        disbursement_ref=_refs(db, Disbursement, {alert.disbursement_id}).get(alert.disbursement_id),  # type: ignore[arg-type]
        verification_id=alert.verification_id,
        verification_ref=_refs(db, IdentityVerification, {alert.verification_id}).get(alert.verification_id),  # type: ignore[arg-type]
        triage_note=alert.triage_note,
        triaged_by=triager.full_name if triager else None,
        triaged_at=alert.triaged_at,
    )
