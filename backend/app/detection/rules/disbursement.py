"""Disbursement rules: shared payment destinations, last-minute destination changes, outliers and bursts."""

from __future__ import annotations

from datetime import timedelta

from app.detection.context import DetectionContext
from app.detection.signals import Signal
from app.detection.versions import RULES_VERSION
from app.models import Disbursement, FinancialAidApplication
from app.models.enums import Severity, SignalCategory, VerificationOutcome

OUTLIER_Z = 3.5
CHANGE_WINDOW = timedelta(days=30)
URGENT_CHANGE_WINDOW = timedelta(days=7)
BURST_WINDOW = timedelta(days=7)


def evaluate_disbursement(ctx: DetectionContext, d: Disbursement) -> list[Signal]:
    signals: list[Signal] = []

    others = ctx.destination_students.get(d.destination_id, set()) - {d.student_id}
    if others:
        same, other = ctx.split_by_org(others, d.organization_id)
        signals.append(
            Signal(
                code="DESTINATION_SHARED",
                category=SignalCategory.DISBURSEMENT,
                severity=Severity.HIGH if len(others) >= 2 else Severity.MEDIUM,
                weight=0.45 if len(others) >= 2 else 0.25,
                title="Payment destination shared by other students",
                description=(
                    f"The refund destination also receives funds for {len(others)} other student(s)"
                    + (f", including {other} at other institutions" if other else "")
                    + ". Unrelated students rarely share a bank account or prepaid card."
                ),
                version=RULES_VERSION,
                evidence={
                    "students_in_institution": same,
                    "students_at_other_institutions": other,
                    "disbursement": d.reference,
                },
            )
        )

    if d.destination_changed_at and timedelta(0) <= d.disbursed_at - d.destination_changed_at <= CHANGE_WINDOW:
        lead = d.disbursed_at - d.destination_changed_at
        verified = any(
            v.status == VerificationOutcome.PASSED
            and v.completed_at is not None
            and d.destination_changed_at <= v.completed_at <= d.disbursed_at
            for v in ctx.student_verifications.get(d.student_id, [])
        )
        if verified:
            signals.append(
                Signal(
                    code="DESTINATION_CHANGE_VERIFIED",
                    category=SignalCategory.DISBURSEMENT,
                    severity=Severity.INFO,
                    weight=0.02,
                    title="Destination change confirmed by step-up verification",
                    description=(
                        "The account owner passed identity verification after changing the payment destination."
                    ),
                    version=RULES_VERSION,
                    evidence={"disbursement": d.reference},
                )
            )
        else:
            urgent = lead <= URGENT_CHANGE_WINDOW
            signals.append(
                Signal(
                    code="DESTINATION_CHANGED_BEFORE_PAYOUT",
                    category=SignalCategory.DISBURSEMENT,
                    severity=Severity.MEDIUM if urgent else Severity.LOW,
                    weight=0.30 if urgent else 0.1,
                    title="Payment destination changed shortly before payout",
                    description=(
                        f"The destination was changed {lead.days} day(s) before {d.reference} without a successful "
                        "identity verification in between."
                    ),
                    version=RULES_VERSION,
                    evidence={"days_before_payout": lead.days, "disbursement": d.reference},
                )
            )

    median, mad = ctx.amount_stats.get(d.fund_type, (float(d.amount), 1.0))
    z = (float(d.amount) - median) / mad
    if z >= OUTLIER_Z:
        signals.append(
            Signal(
                code="AMOUNT_OUTLIER",
                category=SignalCategory.DISBURSEMENT,
                severity=Severity.HIGH,
                weight=0.35,
                title="Disbursement amount far above typical",
                description=(
                    f"{d.reference} for ${float(d.amount):,.0f} is {z:.1f} robust standard deviations "
                    "above the typical "
                    f"{d.fund_type.replace('_', ' ')} of ${median:,.0f}."
                ),
                version=RULES_VERSION,
                evidence={"amount": float(d.amount), "typical": round(median), "robust_z": round(z, 1)},
            )
        )

    window = [
        x
        for x in ctx.student_disbursements.get(d.student_id, [])
        if abs(x.disbursed_at - d.disbursed_at) <= BURST_WINDOW
    ]
    distinct_days = {x.disbursed_at.date() for x in window}
    if len(distinct_days) >= 3:
        signals.append(
            Signal(
                code="DISBURSEMENT_BURST",
                category=SignalCategory.DISBURSEMENT,
                severity=Severity.MEDIUM,
                weight=0.2,
                title="Burst of disbursements within a week",
                description=f"{len(window)} disbursements on {len(distinct_days)} different days within seven days.",
                version=RULES_VERSION,
                evidence={"disbursements_in_window": len(window)},
            )
        )
    return signals


def evaluate(ctx: DetectionContext, app: FinancialAidApplication) -> list[Signal]:
    signals: list[Signal] = []
    for d in ctx.student_disbursements.get(app.student_id, []):
        if d.application_id == app.id:
            signals.extend(evaluate_disbursement(ctx, d))
    return signals
