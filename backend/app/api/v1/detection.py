from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require, scoped
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.permissions import P
from app.detection.anomaly import FEATURES, FLAG_PERCENTILE, MAX_WEIGHT
from app.detection.catalog import PRINCIPLES, RULES
from app.detection.signals import LEVEL_THRESHOLDS
from app.detection.versions import ENGINE_METHOD, GRAPH_VERSION, MODEL_VERSION, RULES_VERSION
from app.models import DetectionRun, FinancialAidApplication, FraudSignal, RiskAssessment
from app.models.enums import AuditCategory
from app.schemas.risk import DetectionRunOut, DetectionStatus, ModelCardOut, RuleOut, ScenarioCheck
from app.services import audit, detection_runs
from app.workers.jobs import enqueue_detection_run

router = APIRouter(prefix="/detection", tags=["detection"])

Reader = Annotated[Principal, Depends(require(P.DASHBOARD_READ))]

SCENARIO_EXPECTATIONS: dict[str, tuple[str, str, list[str]]] = {
    "identity_impersonation": ("Identity impersonation", "fraud", ["FACE_MISMATCH", "DESTINATION_SHARED"]),
    "duplicate_identity": ("Duplicate applications", "fraud", ["SSN_IDENTITY_CONFLICT", "DEVICE_BURST"]),
    "shared_destination": ("Suspicious payment destination", "fraud", ["DESTINATION_SHARED"]),
    "unusual_disbursement": ("Unusual disbursement", "fraud", ["AMOUNT_OUTLIER", "DISBURSEMENT_BURST"]),
    "coordinated_network": ("Coordinated fraud network", "fraud", ["NETWORK_CLUSTER", "DEVICE_BURST", "NO_ATTENDANCE"]),
    "control_siblings": ("Siblings sharing a household", "control", []),
    "control_dorm": ("Residence hall address", "control", []),
    "control_transfer": ("Transfer student", "control", []),
    "control_bank_change": ("Verified bank change", "control", []),
    "control_high_need": ("High-need independent student", "control", []),
}


def _runs(db: DB, principal: Principal):  # type: ignore[no-untyped-def]
    stmt = select(DetectionRun).order_by(DetectionRun.created_at.desc())
    if principal.org_id is not None:
        stmt = stmt.where((DetectionRun.organization_id == principal.org_id) | DetectionRun.organization_id.is_(None))
    return stmt


@router.get("/status", response_model=DetectionStatus, summary="Engine versions, recent runs, model card and rules")
def status(db: DB, principal: Reader) -> DetectionStatus:
    recent = db.scalars(_runs(db, principal).limit(5)).all()
    assessed = db.scalar(
        scoped(select(func.count()).select_from(FinancialAidApplication), FinancialAidApplication, principal).where(
            FinancialAidApplication.risk_score.is_not(None)
        )
    )
    total_apps = db.scalar(select(func.count()).select_from(FinancialAidApplication)) or 0
    return DetectionStatus(
        method=ENGINE_METHOD,
        rules_version=RULES_VERSION,
        model_version=MODEL_VERSION,
        graph_version=GRAPH_VERSION,
        jobs_backend=get_settings().jobs_backend,
        last_run=DetectionRunOut.model_validate(recent[0]) if recent else None,
        recent_runs=[DetectionRunOut.model_validate(r) for r in recent],
        assessed_applications=assessed or 0,
        model_card=ModelCardOut(
            version=MODEL_VERSION,
            algorithm="Isolation Forest (scikit-learn, 200 trees), retrained on every run",
            trained_on=f"{total_apps} synthetic applications (platform-wide); no real student data",
            features=[label for _, label in FEATURES],
            excluded_features=["income / Student Aid Index", "dependency status", "age", "demographics", "geography"],
            explanation_method="Occlusion: each feature replaced by its training median; score change = contribution",
            max_weight=MAX_WEIGHT,
            evaluation=(
                "Not evaluated against real-world fraud labels. No accuracy metric is claimed. Flags the top "
                f"{(1 - FLAG_PERCENTILE):.0%} most unusual records, with capped influence on the final score."
            ),
        ),
        rules=[RuleOut(**r.__dict__) for r in RULES],
        level_thresholds={level.value: threshold for threshold, level in LEVEL_THRESHOLDS},
        principles=PRINCIPLES,
    )


@router.post("/runs", response_model=DetectionRunOut, status_code=202, summary="Start a detection run (background job)")
def start_run(
    request: Request,
    background: BackgroundTasks,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.DETECTION_RUN))],
) -> DetectionRun:
    run = detection_runs.create_run(db, organization_id=principal.org_id, user=principal.user)
    audit.record(
        db,
        category=AuditCategory.DETECTION,
        action="detection.run_requested",
        actor=principal.user,
        organization_id=principal.org_id,
        target_type="detection_run",
        target_id=run.id,
        request=request,
    )
    db.commit()
    run.mode = enqueue_detection_run(run.id, background)
    db.commit()
    return run


@router.get("/runs/{run_id}", response_model=DetectionRunOut, summary="Detection run status")
def get_run(run_id: uuid.UUID, db: DB, principal: Reader) -> DetectionRun:
    run = db.get(DetectionRun, run_id)
    if run is None or (principal.org_id is not None and run.organization_id not in (principal.org_id, None)):
        raise NotFoundError("Detection run not found.")
    return run


@router.get(
    "/scenario-validation",
    response_model=list[ScenarioCheck],
    summary="Checks that each documented demo scenario triggers its expected signals (not an accuracy metric)",
)
def scenario_validation(db: DB, principal: Reader) -> list[ScenarioCheck]:
    apps = db.scalars(
        scoped(select(FinancialAidApplication), FinancialAidApplication, principal).where(
            FinancialAidApplication.scenario_key.is_not(None)
        )
    ).all()
    by_scenario: dict[str, list[FinancialAidApplication]] = defaultdict(list)
    for a in apps:
        by_scenario[a.scenario_key].append(a)  # type: ignore[index]
    checks = []
    for key, (label, kind, expected_signals) in SCENARIO_EXPECTATIONS.items():
        members = by_scenario.get(key, [])
        if not members:
            continue
        levels = Counter(a.risk_level or "unassessed" for a in members)
        codes = set(
            db.scalars(
                select(FraudSignal.code)
                .join(RiskAssessment, RiskAssessment.id == FraudSignal.assessment_id)
                .where(RiskAssessment.application_id.in_([a.id for a in members]), RiskAssessment.is_current)
                .distinct()
            )
        )
        if kind == "fraud":
            passed = all(a.risk_level in ("high", "critical") for a in members) and any(
                c in codes for c in expected_signals
            )
            expected = "Every application rated high or critical"
        else:
            passed = all(a.risk_level in ("low", "medium") for a in members)
            expected = "No application rated high or critical (legitimate activity)"
        checks.append(
            ScenarioCheck(
                scenario=key,
                label=label,
                kind=kind,  # type: ignore[arg-type]
                applications=len(members),
                expected=expected,
                expected_signals=expected_signals,
                observed_levels=dict(levels),
                observed_signals=sorted(codes),
                passed=passed,
            )
        )
    return checks
