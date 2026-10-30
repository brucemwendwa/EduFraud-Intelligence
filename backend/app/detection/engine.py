"""Detection engine: orchestrates rules, graph analysis and the anomaly model into explainable assessments.

Usage:
    engine = DetectionEngine(db).prepare()
    engine.assess(application, triggered_by="user", user=current_user)
    engine.run(org_id=None)            # every application (in scope) — used by detection runs
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.detection import graph
from app.detection.anomaly import FEATURES, AnomalyModel
from app.detection.context import DetectionContext, build_context
from app.detection.rules import application, biometric, disbursement, enrollment, identity
from app.detection.signals import RECOMMENDATIONS, Signal, combine, dedupe, explain, level_for
from app.detection.versions import ENGINE_METHOD, MODEL_VERSION, RULES_VERSION
from app.models import Disbursement, FinancialAidApplication, FraudSignal, RiskAssessment, User
from app.models.enums import RiskLevel, VerificationOutcome
from app.services import alerts as alert_service

RULE_MODULES = (identity, application, enrollment, disbursement, biometric)


@dataclass
class Evaluation:
    score: float
    level: RiskLevel
    signals: list[Signal]
    explanation: str
    recommendation: str
    features: dict[str, float]


@dataclass
class RunStats:
    applications_scored: int = 0
    disbursements_scored: int = 0
    alerts_created: int = 0
    assessments_changed: int = 0


class DetectionEngine:
    def __init__(self, db: Session, now: datetime | None = None) -> None:
        self.db = db
        self.now = now or utcnow()
        self.ctx: DetectionContext
        self.clusters: dict[uuid.UUID, graph.Cluster]
        self.model: AnomalyModel

    def prepare(self) -> DetectionEngine:
        self.ctx = build_context(self.db, self.now)
        self.clusters = graph.find_clusters(graph.link_graph(self.ctx))
        self.model = AnomalyModel(self.ctx)
        return self

    # ---------------------------------------------------------------- evaluation (pure)
    def evaluate(self, app: FinancialAidApplication) -> Evaluation:
        raw: list[Signal] = []
        for module in RULE_MODULES:
            raw.extend(module.evaluate(self.ctx, app))
        raw.extend(graph.evaluate(self.clusters, app))
        raw.extend(self.model.evaluate(app))
        signals = dedupe(raw)
        score = combine(signals)
        level = level_for(score)
        features = {}
        if app.id in self.model.index:
            row = self.model.X[self.model.index[app.id]]
            features = {name: float(row[i]) for i, (name, _) in enumerate(FEATURES)}
        return Evaluation(score, level, signals, explain(score, level, signals), RECOMMENDATIONS[level], features)

    def evaluate_disbursement(self, d: Disbursement) -> tuple[float, list[str]]:
        signals = dedupe(disbursement.evaluate_disbursement(self.ctx, d))
        meaningful = [s for s in signals if s.weight >= 0.05]
        return combine(meaningful), [s.title for s in meaningful]

    # ---------------------------------------------------------------- persistence
    def assess(
        self,
        app: FinancialAidApplication,
        *,
        triggered_by: str,
        user: User | None = None,
        at: datetime | None = None,
    ) -> tuple[RiskAssessment, bool, bool]:
        """Scores and persists. Returns (current assessment, changed, alert_created)."""
        result = self.evaluate(app)
        current = self.db.scalar(
            select(RiskAssessment).where(RiskAssessment.application_id == app.id, RiskAssessment.is_current)
        )
        app.last_assessed_at = at or self.now
        same = (
            current is not None
            and abs(current.score - result.score) < 0.5
            and sorted(s.code for s in current.signals) == sorted(s.code for s in result.signals)
        )
        if same:
            assessment, changed = current, False
        else:
            if current is not None:
                current.is_current = False
            assessment = RiskAssessment(
                organization_id=app.organization_id,
                subject_type="application",
                application_id=app.id,
                score=result.score,
                level=result.level,
                method=ENGINE_METHOD,
                rules_version=RULES_VERSION,
                model_version=MODEL_VERSION if self.model.model is not None else None,
                explanation=result.explanation,
                recommended_action=result.recommendation,
                feature_snapshot=result.features,
                triggered_by=triggered_by,
                triggered_by_user_id=user.id if user else None,
                is_current=True,
                created_at=at or self.now,
            )
            assessment.signals = [
                FraudSignal(
                    organization_id=app.organization_id,
                    code=s.code,
                    category=s.category,
                    severity=s.severity,
                    weight=s.weight,
                    points=s.points,
                    title=s.title,
                    description=s.description,
                    evidence=s.evidence,
                    method=s.method,
                    version=s.version,
                    created_at=at or self.now,
                )
                for s in result.signals
            ]
            self.db.add(assessment)
            self.db.flush()
            changed = True
        app.risk_score = result.score
        app.risk_level = result.level

        riskiest = self._score_disbursements(app)
        failed = [
            v for v in self.ctx.student_verifications.get(app.student_id, []) if v.status == VerificationOutcome.FAILED
        ]
        _, created = alert_service.upsert_for_assessment(
            self.db,
            app,
            assessment,
            result.signals,
            disbursement_id=riskiest.id if riskiest else None,
            verification_id=failed[-1].id if failed else None,
        )
        return assessment, changed, created

    def _score_disbursements(self, app: FinancialAidApplication) -> Disbursement | None:
        riskiest, best = None, 0.0
        for d in self.ctx.student_disbursements.get(app.student_id, []):
            if d.application_id != app.id:
                continue
            score, flags = self.evaluate_disbursement(d)
            d.risk_score, d.risk_flags = score, flags
            if score > best:
                riskiest, best = d, score
        return riskiest if best >= 30 else None

    def run(
        self, org_id: uuid.UUID | None = None, *, triggered_by: str = "detection_run", user: User | None = None
    ) -> RunStats:
        stats = RunStats()
        for app in self.ctx.applications:
            if org_id is not None and app.organization_id != org_id:
                continue
            _, changed, created = self.assess(app, triggered_by=triggered_by, user=user)
            stats.applications_scored += 1
            stats.assessments_changed += int(changed)
            stats.alerts_created += int(created)
            stats.disbursements_scored += sum(
                1 for d in self.ctx.student_disbursements.get(app.student_id, []) if d.application_id == app.id
            )
        return stats
