"""Human-readable catalogue of every signal the engine can emit (served by /detection/status and documented)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleInfo:
    code: str
    category: str
    method: str
    max_weight: float
    description: str


RULES: tuple[RuleInfo, ...] = (
    RuleInfo(
        "SSN_IDENTITY_CONFLICT", "identity", "rule", 0.55, "One SSN token behind different names or dates of birth."
    ),
    RuleInfo("CONTACT_REUSE", "identity", "rule", 0.25, "Phone or email shared with students at a different address."),
    RuleInfo(
        "SHARED_HOUSEHOLD_OR_RESIDENCE",
        "identity",
        "rule",
        0.04,
        "Shared address/household: deliberately near-zero weight.",
    ),
    RuleInfo("DEVICE_BURST", "application", "rule", 0.40, ">= 3 applications from one device within 72 hours."),
    RuleInfo(
        "NETWORK_BURST", "application", "rule", 0.20, ">= 3 applications from one network address within 72 hours."
    ),
    RuleInfo(
        "SHARED_DEVICE_SPREAD", "application", "rule", 0.03, "Shared device used over months (e.g. campus kiosk)."
    ),
    RuleInfo(
        "OFF_HOURS_SUBMISSION", "application", "rule", 0.05, "Submitted between midnight and 5 a.m. (context only)."
    ),
    RuleInfo("NO_ATTENDANCE", "enrollment", "rule", 0.35, "No attendance recorded two weeks into the term."),
    RuleInfo(
        "CONCURRENT_ENROLLMENT", "enrollment", "rule", 0.25, "Same identity actively enrolled elsewhere this term."
    ),
    RuleInfo(
        "DESTINATION_SHARED", "disbursement", "rule", 0.45, "Refund destination receives funds for other students."
    ),
    RuleInfo(
        "DESTINATION_CHANGED_BEFORE_PAYOUT",
        "disbursement",
        "rule",
        0.30,
        "Destination changed shortly before payout without verification.",
    ),
    RuleInfo(
        "DESTINATION_CHANGE_VERIFIED",
        "disbursement",
        "rule",
        0.02,
        "Destination change confirmed by step-up verification.",
    ),
    RuleInfo(
        "AMOUNT_OUTLIER",
        "disbursement",
        "rule",
        0.35,
        "Amount >= 3.5 robust standard deviations above typical for the fund.",
    ),
    RuleInfo("DISBURSEMENT_BURST", "disbursement", "rule", 0.20, "Disbursements on >= 3 different days within a week."),
    RuleInfo("FACE_MISMATCH", "biometric", "biometric", 0.60, "Step-up verification face similarity below threshold."),
    RuleInfo("PRESENTATION_ATTACK", "biometric", "biometric", 0.50, "Liveness check detected a spoofing attempt."),
    RuleInfo("DOCUMENT_SUSPICIOUS", "biometric", "biometric", 0.35, "Identity document failed authenticity checks."),
    RuleInfo("NETWORK_CLUSTER", "network", "graph", 0.40, "Member of a linked cluster of >= 4 applications."),
    RuleInfo(
        "ANOMALY_MODEL",
        "anomaly",
        "anomaly_model",
        0.30,
        "Top 4% most unusual by the Isolation Forest (capped influence).",
    ),
)

PRINCIPLES = [
    "Decision support only: scores and alerts are recommendations; people make every adverse decision.",
    "No signal uses income, Student Aid Index, dependency status, age, or any demographic attribute.",
    "Benign sharing (households, residence halls, campus kiosks, verified bank changes) carries near-zero weight.",
    "Every assessment records its signals, points, method, rule and model versions, and timestamp.",
    "Cross-institution matches reveal only that a match exists — never another institution's records.",
]
