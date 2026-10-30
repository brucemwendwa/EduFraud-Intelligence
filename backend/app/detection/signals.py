"""Signals and explainable score combination.

Each detection rule emits `Signal`s with a weight in (0, 1): the probability-like
strength of that evidence on its own. Signals are combined with a noisy-OR

    score = 100 * (1 - Π (1 - w_i))

so independent weak signals add up, a single strong one dominates, and the score
can never exceed 100. Each signal's share of the score ("points") is its
log-odds contribution  -ln(1 - w_i)  normalised to the final score, which makes the
points sum exactly to the score — the explanation is a faithful decomposition.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import RiskLevel, Severity


@dataclass
class Signal:
    code: str
    category: str
    severity: Severity
    weight: float
    title: str
    description: str
    method: str = "rule"
    version: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    points: float = 0.0


LEVEL_THRESHOLDS = ((80.0, RiskLevel.CRITICAL), (60.0, RiskLevel.HIGH), (30.0, RiskLevel.MEDIUM))

RECOMMENDATIONS = {
    RiskLevel.LOW: "No action needed. Continue routine processing.",
    RiskLevel.MEDIUM: "Review the listed signals before the next disbursement.",
    RiskLevel.HIGH: "Human review required before disbursement. Consider step-up identity verification.",
    RiskLevel.CRITICAL: (
        "Hold pending disbursements and open an investigation. No adverse action may be taken without human review."
    ),
}


def level_for(score: float) -> RiskLevel:
    for threshold, level in LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return RiskLevel.LOW


def combine(signals: list[Signal]) -> float:
    """Noisy-OR combination; assigns each signal its exact share of the score (in place)."""
    if not signals:
        return 0.0
    capped = [min(max(s.weight, 0.0), 0.99) for s in signals]
    remainder = math.prod(1 - w for w in capped)
    score = round(100 * (1 - remainder), 1)
    log_odds = [-math.log(1 - w) for w in capped]
    total = sum(log_odds) or 1.0
    for s, lo in zip(signals, log_odds, strict=True):
        s.points = round(score * lo / total, 1)
    return score


def dedupe(signals: list[Signal]) -> list[Signal]:
    """Keep the strongest signal per code (e.g. several disbursements raising the same flag)."""
    best: dict[str, Signal] = {}
    for s in signals:
        if s.code not in best or s.weight > best[s.code].weight:
            best[s.code] = s
    return sorted(best.values(), key=lambda s: s.weight, reverse=True)


def explain(score: float, level: RiskLevel, signals: list[Signal]) -> str:
    if not signals:
        return "No risk signals were detected for this record."
    drivers = [s for s in signals if s.points >= 1.0][:4] or signals[:1]
    parts = "; ".join(f"{s.title.lower()} (+{s.points:.0f})" for s in drivers)
    return f"Score {score:.0f}/100 ({level.value}). Main drivers: {parts}."
