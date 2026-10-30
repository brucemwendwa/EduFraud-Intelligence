"""End-to-end seeding: synthetic records → detection run → realistic alert timeline.

Shared by `python -m app.seed` and the test suite so demos and tests see identical data.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.detection.engine import DetectionEngine, RunStats
from app.detection.versions import MODEL_VERSION, RULES_VERSION
from app.models import Alert, DetectionRun, Disbursement, FinancialAidApplication, Organization, RiskAssessment
from app.models.enums import RunStatus
from app.seed.generator import GenerationSummary, SyntheticGenerator


def seed_synthetic(db: Session, orgs: dict[str, Organization]) -> tuple[GenerationSummary, RunStats]:
    summary = SyntheticGenerator(db, orgs).run()
    db.flush()
    seed_verification_events(db)
    stats = run_seed_detection(db)
    backdate_alerts(db)
    return summary, stats


def seed_verification_events(db: Session) -> None:
    """Runs the planted verification attempts through the real verification service."""
    from app.services.verification import run_biometric

    target = db.scalar(
        select(FinancialAidApplication).where(FinancialAidApplication.scenario_key == "identity_impersonation")
    )
    if target is not None:
        refund = db.scalar(
            select(Disbursement).where(
                Disbursement.application_id == target.id, Disbursement.destination_changed_at.is_not(None)
            )
        )
        attempt_at = (refund.destination_changed_at if refund else utcnow()) + timedelta(minutes=4)  # type: ignore[operator]
        # Someone else requested the refund-destination change and failed step-up verification.
        run_biometric(
            db,
            app=target,
            trigger="payment_destination_change",
            sample_key="impostor_screen_replay",
            user=None,
            at=attempt_at,
        )

    # Everyday outcomes: a few glare retries and one printed-photo attempt later resolved in person.
    consented = db.scalars(
        select(FinancialAidApplication)
        .join(FinancialAidApplication.student)
        .where(FinancialAidApplication.scenario_key.is_(None), FinancialAidApplication.status == "approved")
        .order_by(FinancialAidApplication.reference)
    ).all()
    candidates = [a for a in consented if a.student.biometric_consent][:6]
    now = utcnow()
    for i, app in enumerate(candidates[:4]):
        when = now - timedelta(days=5 + i * 9, hours=i)
        run_biometric(db, app=app, trigger="new_device_login", sample_key="unreadable_document", user=None, at=when)
        run_biometric(
            db,
            app=app,
            trigger="new_device_login",
            sample_key="enrolled_student",
            user=None,
            at=when + timedelta(minutes=7),
        )
    db.flush()


def run_seed_detection(db: Session) -> RunStats:
    started = utcnow()
    stats = DetectionEngine(db).prepare().run(triggered_by="detection_run")
    db.add(
        DetectionRun(
            status=RunStatus.COMPLETED,
            mode="inline",
            rules_version=RULES_VERSION,
            model_version=MODEL_VERSION,
            applications_scored=stats.applications_scored,
            disbursements_scored=stats.disbursements_scored,
            alerts_created=stats.alerts_created,
            created_at=started,
            started_at=started,
            finished_at=utcnow(),
        )
    )
    db.flush()
    return stats


def backdate_alerts(db: Session, seed: int = 7) -> None:
    """Dates each seeded alert to when continuous monitoring would have raised it.

    Without this every synthetic alert would share the seeding timestamp; dating them to the
    triggering activity (submission, payment or verification) gives the dashboard a realistic
    timeline. Only synthetic, seeded data is touched.
    """
    rng = random.Random(seed)
    now = utcnow()
    for alert in db.scalars(select(Alert)):
        app = db.get(FinancialAidApplication, alert.application_id)
        if app is None:
            continue
        moments: list[datetime] = [app.submitted_at]
        for d in db.scalars(select(Disbursement).where(Disbursement.application_id == app.id)):
            if not d.risk_score or d.risk_score < 30:
                continue
            if d.disbursed_at <= now:
                moments.append(d.disbursed_at)
            if d.destination_changed_at and d.destination_changed_at <= now:
                moments.append(d.destination_changed_at)  # monitoring reacts to the change itself
        when = min(max(moments) + timedelta(hours=rng.uniform(0.5, 6)), now - timedelta(minutes=rng.uniform(5, 90)))
        alert.created_at = alert.updated_at = when
        assessment = db.get(RiskAssessment, alert.assessment_id) if alert.assessment_id else None
        if assessment is not None:
            assessment.created_at = when
            for signal in assessment.signals:
                signal.created_at = when
            app.last_assessed_at = when
    db.flush()
