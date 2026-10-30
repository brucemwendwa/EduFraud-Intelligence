"""Detection runs: create, execute (in a worker or inline) and record outcomes."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.types import utcnow
from app.detection.engine import DetectionEngine
from app.detection.versions import MODEL_VERSION, RULES_VERSION
from app.models import DetectionRun, User
from app.models.enums import AuditCategory, AuditOutcome, RunStatus
from app.services import audit

logger = logging.getLogger("edushield.detection")


def create_run(db: Session, *, organization_id: uuid.UUID | None, user: User | None) -> DetectionRun:
    run = DetectionRun(
        organization_id=organization_id,
        status=RunStatus.QUEUED,
        mode=get_settings().jobs_backend,
        triggered_by_id=user.id if user else None,
        rules_version=RULES_VERSION,
        model_version=MODEL_VERSION,
    )
    db.add(run)
    db.flush()
    return run


def execute_run(run_id: uuid.UUID) -> None:
    """Runs the engine in its own session. Safe to call from a Celery worker or a background task."""
    with SessionLocal() as db:
        run = db.get(DetectionRun, run_id)
        if run is None or run.status not in (RunStatus.QUEUED, RunStatus.FAILED):
            return
        run.status = RunStatus.RUNNING
        run.started_at = utcnow()
        db.commit()
        user = db.get(User, run.triggered_by_id) if run.triggered_by_id else None
        try:
            stats = DetectionEngine(db).prepare().run(run.organization_id, triggered_by="detection_run", user=user)
            run.applications_scored = stats.applications_scored
            run.disbursements_scored = stats.disbursements_scored
            run.alerts_created = stats.alerts_created
            run.status = RunStatus.COMPLETED
            outcome = AuditOutcome.SUCCESS
        except Exception as exc:  # noqa: BLE001 - recorded on the run and in the audit trail
            logger.exception("detection_run_failed", extra={"run_id": str(run_id)})
            db.rollback()
            run = db.get(DetectionRun, run_id)
            assert run is not None
            run.status = RunStatus.FAILED
            run.error = str(exc)[:500]
            outcome = AuditOutcome.FAILURE
        run.finished_at = utcnow()
        audit.record(
            db,
            category=AuditCategory.DETECTION,
            action="detection.run",
            outcome=outcome,
            actor=user,
            organization_id=run.organization_id,
            target_type="detection_run",
            target_id=run.id,
            details={
                "applications_scored": run.applications_scored,
                "alerts_created": run.alerts_created,
                "mode": run.mode,
                "rules_version": run.rules_version,
            },
        )
        db.commit()
