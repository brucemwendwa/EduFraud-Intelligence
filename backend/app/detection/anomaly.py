"""Unsupervised anomaly detection (Isolation Forest) with occlusion-based explanations.

MODEL CARD
  * Purpose: surface applications whose *combination* of behavioural features is unusual,
    complementing the rules (which catch known patterns).
  * Training data: the current synthetic dataset only, retrained on every detection run.
  * Evaluation: NOT evaluated against real-world fraud labels. No accuracy is claimed.
  * Fairness: features describe behaviour (sharing, timing, attendance, payment patterns).
    Income, Student Aid Index, dependency status, age and demographics are excluded.
  * Explanation: each feature is replaced in turn by its training median ("occlusion");
    the change in anomaly score is that feature's contribution. Top contributors are shown.
  * Influence: capped at a weight of 0.30, so the model can raise attention but never on
    its own drive a record to "critical".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

from app.detection.context import DetectionContext
from app.detection.rules.application import burst_peers
from app.detection.signals import Signal
from app.detection.versions import MODEL_VERSION
from app.models import FinancialAidApplication
from app.models.enums import EnrollmentStatus, Modality, Severity, SignalCategory, VerificationOutcome

FEATURES: list[tuple[str, str]] = [
    ("ssn_shared", "SSN token shared with other records"),
    ("contact_shared", "phone/email shared with other students"),
    ("device_burst", "applications from the same device within 72 h"),
    ("network_burst", "applications from the same network within 72 h"),
    ("off_hours", "submitted between midnight and 5 a.m."),
    ("online_only", "online-only enrollment"),
    ("no_attendance", "no recorded attendance"),
    ("credit_hours", "enrolled credit hours"),
    ("amount_z", "largest disbursement vs. typical amount"),
    ("destination_shared", "other students paid to the same destination"),
    ("destination_changed", "destination changed shortly before payout"),
    ("disbursements", "number of disbursements"),
    ("verification_failed", "failed identity verification"),
]
FLAG_PERCENTILE = 0.96
MAX_WEIGHT = 0.30


def featurize(ctx: DetectionContext, app: FinancialAidApplication) -> list[float]:
    sid = app.student_id
    disb = [d for d in ctx.student_disbursements.get(sid, []) if d.application_id == app.id]
    enroll = [e for e in ctx.student_enrollments.get(sid, []) if e.application_id == app.id]
    amount_z = 0.0
    for d in disb:
        median, mad = ctx.amount_stats.get(d.fund_type, (float(d.amount), 1.0))
        amount_z = max(amount_z, (float(d.amount) - median) / mad)
    dest_shared = max((len(ctx.destination_students.get(d.destination_id, set())) - 1 for d in disb), default=0)
    changed = any(
        d.destination_changed_at is not None and (d.disbursed_at - d.destination_changed_at).days <= 7 for d in disb
    )
    return [
        float(len(ctx.others_with_token(sid, "ssn"))),
        float(len(ctx.others_with_token(sid, "phone") | ctx.others_with_token(sid, "email"))),
        float(len(burst_peers(app, ctx.device_apps.get(app.device_token or "", [])))),
        float(len(burst_peers(app, ctx.ip_apps.get(app.ip_token or "", [])))),
        1.0 if app.submitted_at.hour < 5 else 0.0,
        1.0 if any(e.modality == Modality.ONLINE for e in enroll) else 0.0,
        1.0
        if any(e.status == EnrollmentStatus.NEVER_ATTENDED or e.last_attendance_at is None for e in enroll)
        else 0.0,
        float(max((e.credit_hours for e in enroll), default=0)),
        max(amount_z, 0.0),
        float(max(dest_shared, 0)),
        1.0 if changed else 0.0,
        float(len(disb)),
        1.0 if any(v.status == VerificationOutcome.FAILED for v in ctx.student_verifications.get(sid, [])) else 0.0,
    ]


@dataclass
class ModelCard:
    version: str
    trained_on: int
    features: list[str]
    flag_percentile: float
    max_weight: float
    evaluation: str = "Not evaluated on real-world data; trained on synthetic records only. No accuracy is claimed."


class AnomalyModel:
    def __init__(self, ctx: DetectionContext) -> None:
        self.ids: list[uuid.UUID] = [a.id for a in ctx.applications]
        self.X = np.array([featurize(ctx, a) for a in ctx.applications], dtype=float)
        self.medians = np.median(self.X, axis=0) if len(self.X) else np.zeros(len(FEATURES))
        self.model: IsolationForest | None = None
        self.percentiles: dict[uuid.UUID, float] = {}
        if len(self.X) >= 20:
            self.model = IsolationForest(n_estimators=200, random_state=7, contamination="auto").fit(self.X)
            scores = -self.model.score_samples(self.X)
            ranks = scores.argsort().argsort() / max(len(scores) - 1, 1)
            self.percentiles = dict(zip(self.ids, ranks.tolist(), strict=True))
        self.index = {app_id: i for i, app_id in enumerate(self.ids)}

    @property
    def card(self) -> ModelCard:
        return ModelCard(
            version=MODEL_VERSION,
            trained_on=len(self.ids) if self.model else 0,
            features=[label for _, label in FEATURES],
            flag_percentile=FLAG_PERCENTILE,
            max_weight=MAX_WEIGHT,
        )

    def explain(self, row: np.ndarray) -> list[tuple[str, float, float]]:
        """Occlusion attribution: (feature label, value, contribution) for features that raise the anomaly score."""
        assert self.model is not None
        variants = np.repeat(row[None, :], len(FEATURES), axis=0)
        variants[np.arange(len(FEATURES)), np.arange(len(FEATURES))] = self.medians
        base = -self.model.score_samples(row[None, :])[0]
        occluded = -self.model.score_samples(variants)
        contributions = base - occluded
        order = np.argsort(-contributions)
        return [(FEATURES[j][1], float(row[j]), float(contributions[j])) for j in order if contributions[j] > 1e-4][:3]

    def evaluate(self, app: FinancialAidApplication) -> list[Signal]:
        if self.model is None or app.id not in self.index:
            return []
        pct = self.percentiles[app.id]
        if pct < FLAG_PERCENTILE:
            return []
        drivers = self.explain(self.X[self.index[app.id]])
        if not drivers:
            return []
        strength = (pct - FLAG_PERCENTILE) / (1 - FLAG_PERCENTILE)
        described = "; ".join(f"{name} ({_fmt(value)})" for name, value, _ in drivers)
        return [
            Signal(
                code="ANOMALY_MODEL",
                category=SignalCategory.ANOMALY,
                severity=Severity.MEDIUM,
                weight=round(0.12 + (MAX_WEIGHT - 0.12) * strength, 3),
                title="Unusual combination of behaviours (anomaly model)",
                description=(
                    f"More unusual than {pct:.0%} of applications. Main contributing features: {described}. "
                    "Unsupervised model trained on synthetic data and not evaluated on real-world data."
                ),
                method="anomaly_model",
                version=MODEL_VERSION,
                evidence={
                    "percentile": round(pct, 3),
                    "attribution": [
                        {"feature": n, "value": round(v, 2), "contribution": round(c, 4)} for n, v, c in drivers
                    ],
                    "explainer": "occlusion (feature replaced by training median)",
                },
            )
        ]


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"
