"""Enrollment rules: no attendance after aid, and overlapping enrollment at several institutions."""

from __future__ import annotations

from datetime import timedelta

from app.detection.context import DetectionContext
from app.detection.signals import Signal
from app.detection.versions import RULES_VERSION
from app.models import FinancialAidApplication
from app.models.enums import EnrollmentStatus, Modality, Severity, SignalCategory

ATTENDANCE_GRACE = timedelta(days=14)


def evaluate(ctx: DetectionContext, app: FinancialAidApplication) -> list[Signal]:
    signals: list[Signal] = []
    enrollments = [e for e in ctx.student_enrollments.get(app.student_id, []) if e.application_id == app.id]
    for e in enrollments:
        started_long_ago = ctx.now.date() - e.term_start > ATTENDANCE_GRACE
        absent = e.status == EnrollmentStatus.NEVER_ATTENDED or (
            e.status == EnrollmentStatus.ENROLLED and e.last_attendance_at is None and started_long_ago
        )
        if absent:
            online = e.modality == Modality.ONLINE
            signals.append(
                Signal(
                    code="NO_ATTENDANCE",
                    category=SignalCategory.ENROLLMENT,
                    severity=Severity.HIGH if online else Severity.MEDIUM,
                    weight=0.35 if online else 0.25,
                    title="No recorded attendance" + (" in an online-only enrollment" if online else ""),
                    description=(
                        f"Enrolled in {e.term} ({e.credit_hours} credits, {e.modality.replace('_', ' ')}) with no "
                        "attendance recorded more than two weeks after the term started."
                    ),
                    version=RULES_VERSION,
                    evidence={"term": e.term, "modality": e.modality, "credit_hours": e.credit_hours},
                )
            )

    # The same person (consistent SSN + name + DOB tokens) enrolled elsewhere in the same term.
    mine = ctx.student_tokens.get(app.student_id, {})
    same_person = {
        s
        for s in ctx.others_with_token(app.student_id, "ssn")
        if ctx.student_tokens.get(s, {}).get("dob") == mine.get("dob")
        and ctx.student_tokens.get(s, {}).get("name") == mine.get("name")
    }
    my_terms = {e.term for e in enrollments}
    overlapping = [
        e
        for s in same_person
        for e in ctx.student_enrollments.get(s, [])
        if e.term in my_terms and e.status in (EnrollmentStatus.ENROLLED, EnrollmentStatus.NEVER_ATTENDED)
    ]
    if overlapping:
        signals.append(
            Signal(
                code="CONCURRENT_ENROLLMENT",
                category=SignalCategory.ENROLLMENT,
                severity=Severity.MEDIUM,
                weight=0.25,
                title="Enrolled at another institution in the same term",
                description="The same identity holds an active enrollment at another institution for this term.",
                version=RULES_VERSION,
                evidence={"other_institutions": len({e.organization_id for e in overlapping})},
            )
        )
    return signals
