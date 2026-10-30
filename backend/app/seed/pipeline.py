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
    seed_cases(db)
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


def seed_cases(db: Session) -> None:
    """A realistic caseload created through the real case service (so the audit trail is genuine).

    The impersonation and unusual-disbursement alerts are deliberately left without cases for the live demo.
    """
    from app.models import User
    from app.models.enums import CaseDecisionType, CaseResolution
    from app.services import cases

    users = {u.email: u for u in db.scalars(select(User))}
    marcus = users.get("investigator@northbridge.demo")
    dana = users.get("analyst@northbridge.demo")
    elena = users.get("officer@northbridge.demo")
    hannah = users.get("investigator@lakeshore.demo")
    if not all((marcus, dana, elena, hannah)):
        return

    def first(scenario: str | None, org_slug: str, **filters: object) -> FinancialAidApplication | None:
        stmt = (
            select(FinancialAidApplication)
            .join(Organization, Organization.id == FinancialAidApplication.organization_id)
            .where(Organization.slug == org_slug)
            .order_by(FinancialAidApplication.reference)
        )
        stmt = (
            stmt.where(FinancialAidApplication.scenario_key == scenario)
            if scenario
            else stmt.where(FinancialAidApplication.scenario_key.is_(None))
        )
        for column, value in filters.items():
            stmt = stmt.where(getattr(FinancialAidApplication, column) == value)
        return db.scalar(stmt)

    def open_for(app: FinancialAidApplication | None, opener: User, assignee: User | None) -> object | None:
        if app is None:
            return None
        return cases.open_case(
            db,
            opener,
            app=app,
            alert=None,
            title=None,
            fraud_category=None,
            priority=None,
            assignee_id=assignee.id if assignee else None,
            due_at=None,
        )

    dup = open_for(first("duplicate_identity", "northbridge"), marcus, marcus)  # type: ignore[arg-type]
    if dup is not None:
        cases.start_review(db, dup, marcus, None)  # type: ignore[arg-type]
        cases.add_note(
            db,
            dup,
            marcus,
            "Three Northbridge applications and one at another institution share one "  # type: ignore[arg-type]
            "SSN token with different names and birth dates, all submitted from one device within 40 minutes.",
            None,
        )
        cases.decide(
            db,
            dup,
            marcus,
            decision=CaseDecisionType.ESCALATE,
            outcome=None,
            request=None,  # type: ignore[arg-type]
            justification="Identity conflict plus a single-device burst points to a synthetic-identity "
            "scheme. Escalating as suspected fraud; holding any disbursement pending contact with each "
            "applicant through verified channels.",
        )

    shared = open_for(first("shared_destination", "northbridge"), dana, dana)  # type: ignore[arg-type]
    if shared is not None:
        cases.add_note(
            db,
            shared,
            dana,
            "Refunds for four Northbridge students and two elsewhere go to one prepaid "  # type: ignore[arg-type]
            "card. Students reached so far say they did not change their refund preference.",
            None,
        )
        cases.decide(
            db,
            shared,
            dana,
            decision=CaseDecisionType.RESOLVE,  # type: ignore[arg-type]
            outcome=CaseResolution.REFERRED_EXTERNALLY,
            request=None,
            justification="Pattern spans institutions and points to a third party redirecting refunds. "
            "Referred to the compliance office for external review; no finding is made about the students.",
        )

    medium = first(None, "northbridge", risk_level="medium")
    referral = open_for(medium, elena, marcus)  # type: ignore[arg-type]
    if referral is not None:
        cases.add_note(
            db,
            referral,
            marcus,
            "Student confirmed by phone (number on file since enrollment) that they "  # type: ignore[arg-type]
            "changed banks after their old account closed.",
            None,
        )
        cases.decide(
            db,
            referral,
            marcus,
            decision=CaseDecisionType.RESOLVE,  # type: ignore[arg-type]
            outcome=CaseResolution.NO_FRAUD_FOUND,
            request=None,
            justification="Bank change explained and confirmed through a known-good channel. No fraud "
            "found; the medium score reflected an unverified change, which is now verified.",
        )
        cases.decide(
            db,
            referral,
            marcus,
            decision=CaseDecisionType.CLOSE,
            outcome=None,
            request=None,  # type: ignore[arg-type]
            justification="Resolution communicated to the financial aid office; nothing further required.",
        )

    ring = open_for(first("coordinated_network", "lakeshore"), hannah, hannah)  # type: ignore[arg-type]
    if ring is not None:
        cases.start_review(db, ring, hannah, None)  # type: ignore[arg-type]
    db.flush()
