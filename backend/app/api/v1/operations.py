"""Operational visibility for institution administrators and auditors.

Everything here is a count, a state or a code. Student names, document names and contents,
audit details and exception text are deliberately excluded, and every record query is
scoped to the caller's institution.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require, scoped
from app.core.config import get_settings
from app.core.permissions import P
from app.db.types import utcnow
from app.models import (
    ApplicationDocument,
    ApplicationStatusHistory,
    AuditEvent,
    DetectionRun,
    DocumentObjectCleanup,
    DocumentScanJob,
    FinancialAidApplication,
    RiskAssessment,
)
from app.models.enums import ApplicationStatus, DocumentReviewStatus, DocumentStatus, RunStatus
from app.schemas.common import Schema
from app.services.application_lifecycle import AWAITING_REVIEW, OPEN_FOR_REVIEW
from app.services.operations_health import ServiceHealth, overall_status, service_health

router = APIRouter(prefix="/operations", tags=["operations"])

_DECISIONS = (ApplicationStatus.APPROVED.value, ApplicationStatus.REJECTED.value)
_RECENT_LIMIT = 15


class ApplicationProcessing(Schema):
    submitted_24h: int
    submitted_7d: int
    decisions_24h: int
    decisions_7d: int
    awaiting_review: int
    additional_information_required: int
    open_total: int
    oldest_waiting_since: datetime | None


class RiskActivity(Schema):
    assessments_24h: int
    assessments_7d: int
    open_elevated: int
    open_unassessed: int
    last_run_status: str | None
    last_run_finished_at: datetime | None
    failed_runs_7d: int


class DocumentProcessing(Schema):
    pending_scan: int
    scanning: int
    available: int
    rejected: int
    failed: int
    superseded: int
    awaiting_staff_review: int


class JobFailure(Schema):
    kind: Literal["document_scan", "document_cleanup", "detection_run"]
    status: str
    error_code: str | None
    attempts: int | None
    occurred_at: datetime


class JobSummary(Schema):
    scan_queued: int
    scan_running: int
    scan_retrying: int
    scan_failed: int
    cleanup_failed: int
    stalled: int
    recent_failures: list[JobFailure]


class AuditEntry(Schema):
    sequence: int
    occurred_at: datetime
    category: str
    action: str
    outcome: str
    actor_role: str | None


class OperationsOverview(Schema):
    generated_at: datetime
    scope: Literal["institution", "platform"]
    environment: str
    overall_health: Literal["ok", "degraded", "down"]
    health: list[ServiceHealth]
    applications: ApplicationProcessing
    risk: RiskActivity
    documents: DocumentProcessing
    jobs: JobSummary
    recent_audit: list[AuditEntry] | None


def _count(db: DB, principal: Principal, model: type, *where: Any) -> int:
    return db.scalar(scoped(select(func.count()).select_from(model), model, principal).where(*where)) or 0


def _by(db: DB, principal: Principal, model: type, column: Any, *where: Any) -> Counter[str]:
    rows = db.execute(scoped(select(column, func.count()).where(*where).group_by(column), model, principal)).all()
    return Counter({key: count for key, count in rows})


def _runs(principal: Principal):  # type: ignore[no-untyped-def]
    stmt = select(DetectionRun)
    if principal.org_id is not None:
        stmt = stmt.where((DetectionRun.organization_id == principal.org_id) | DetectionRun.organization_id.is_(None))
    return stmt


@router.get("/overview", response_model=OperationsOverview, summary="Service health and processing activity")
def overview(db: DB, principal: Annotated[Principal, Depends(require(P.OPERATIONS_READ))]) -> OperationsOverview:
    now = utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    app, history, doc, job, cleanup = (
        FinancialAidApplication,
        ApplicationStatusHistory,
        ApplicationDocument,
        DocumentScanJob,
        DocumentObjectCleanup,
    )
    submitted = app.submitted_at.is_not(None)
    open_statuses = [s.value for s in OPEN_FOR_REVIEW]

    by_status = _by(db, principal, app, app.status, submitted)
    oldest = db.scalar(
        scoped(select(func.min(app.submitted_at)), app, principal).where(
            app.status.in_([s.value for s in AWAITING_REVIEW])
        )
    )
    applications = ApplicationProcessing(
        submitted_24h=_count(db, principal, app, app.submitted_at >= day),
        submitted_7d=_count(db, principal, app, app.submitted_at >= week),
        decisions_24h=_count(db, principal, history, history.to_status.in_(_DECISIONS), history.created_at >= day),
        decisions_7d=_count(db, principal, history, history.to_status.in_(_DECISIONS), history.created_at >= week),
        awaiting_review=sum(by_status[s.value] for s in AWAITING_REVIEW),
        additional_information_required=by_status[ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED.value],
        open_total=sum(by_status[s] for s in open_statuses),
        oldest_waiting_since=oldest,
    )

    last_run = db.scalars(_runs(principal).order_by(DetectionRun.created_at.desc()).limit(1)).first()
    failed_runs = db.scalars(
        _runs(principal)
        .where(DetectionRun.status == RunStatus.FAILED, DetectionRun.created_at >= week)
        .order_by(DetectionRun.created_at.desc())
    ).all()
    risk = RiskActivity(
        assessments_24h=_count(db, principal, RiskAssessment, RiskAssessment.created_at >= day),
        assessments_7d=_count(db, principal, RiskAssessment, RiskAssessment.created_at >= week),
        open_elevated=_count(
            db, principal, app, submitted, app.status.in_(open_statuses), app.risk_level.in_(("high", "critical"))
        ),
        open_unassessed=_count(db, principal, app, submitted, app.status.in_(open_statuses), app.risk_level.is_(None)),
        last_run_status=last_run.status if last_run else None,
        last_run_finished_at=last_run.finished_at if last_run else None,
        failed_runs_7d=len(failed_runs),
    )

    doc_states = _by(db, principal, doc, doc.status)
    documents = DocumentProcessing(
        pending_scan=doc_states[DocumentStatus.PENDING_SCAN.value],
        scanning=doc_states[DocumentStatus.SCANNING.value],
        available=doc_states[DocumentStatus.AVAILABLE.value],
        rejected=doc_states[DocumentStatus.REJECTED.value],
        failed=doc_states[DocumentStatus.FAILED.value],
        superseded=doc_states[DocumentStatus.SUPERSEDED.value],
        awaiting_staff_review=_count(
            db,
            principal,
            doc,
            doc.status == DocumentStatus.AVAILABLE,
            doc.review_status == DocumentReviewStatus.PENDING,
        ),
    )

    job_states = _by(db, principal, job, job.status)
    cleanup_failed = _count(db, principal, cleanup, cleanup.status == "failed")
    lease = timedelta(seconds=get_settings().document_scan_lease_seconds)
    stalled = _count(db, principal, job, job.status == "running", job.started_at < now - lease) + _count(
        db, principal, job, job.status == "queued", job.created_at < now - lease
    )
    failures = [
        JobFailure(
            kind="document_scan",
            status=j.status,
            error_code=j.error_code,
            attempts=j.attempts,
            occurred_at=j.updated_at,
        )
        for j in db.scalars(
            scoped(select(job), job, principal)
            .where(job.status.in_(("failed", "retry")))
            .order_by(job.updated_at.desc())
            .limit(_RECENT_LIMIT)
        )
    ]
    failures += [
        JobFailure(
            kind="document_cleanup",
            status=c.status,
            error_code=c.error_code,
            attempts=c.attempts,
            occurred_at=c.updated_at,
        )
        for c in db.scalars(
            scoped(select(cleanup), cleanup, principal)
            .where(cleanup.status.in_(("failed", "retry")))
            .order_by(cleanup.updated_at.desc())
            .limit(_RECENT_LIMIT)
        )
    ]
    # Exception text is not returned: it can contain record data. The audit trail and logs hold the detail.
    failures += [
        JobFailure(
            kind="detection_run",
            status=r.status,
            error_code="run_failed",
            attempts=None,
            occurred_at=r.finished_at or r.created_at,
        )
        for r in failed_runs[:_RECENT_LIMIT]
    ]
    failures.sort(key=lambda f: f.occurred_at, reverse=True)

    recent_audit = None
    if principal.can(P.AUDIT_READ):
        stmt = select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(_RECENT_LIMIT)
        if principal.org_id is not None:
            stmt = stmt.where(AuditEvent.organization_id == principal.org_id)
        recent_audit = [
            AuditEntry(
                sequence=e.sequence,
                occurred_at=e.occurred_at,
                category=e.category,
                action=e.action,
                outcome=e.outcome,
                actor_role=e.actor_role,
            )
            for e in db.scalars(stmt)
        ]

    checks = service_health(db)
    return OperationsOverview(
        generated_at=now,
        scope="platform" if principal.org_id is None else "institution",
        environment=get_settings().env,
        overall_health=overall_status(checks),
        health=checks,
        applications=applications,
        risk=risk,
        documents=documents,
        jobs=JobSummary(
            scan_queued=job_states["queued"],
            scan_running=job_states["running"],
            scan_retrying=job_states["retry"],
            scan_failed=job_states["failed"],
            cleanup_failed=cleanup_failed,
            stalled=stalled,
            recent_failures=failures[:_RECENT_LIMIT],
        ),
        recent_audit=recent_audit,
    )
