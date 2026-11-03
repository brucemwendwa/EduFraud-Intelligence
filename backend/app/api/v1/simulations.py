"""Live scenario simulator (demo mode only): replays a synthetic scenario through the real services."""

from __future__ import annotations

import random
from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require, scoped
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import P
from app.models import (
    Alert,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    VerificationRequest,
)
from app.models.enums import AccountStatus, AuditCategory, CardStatus, RiskLevel, StudyMode
from app.schemas.common import Schema
from app.services import audit, scenarios

router = APIRouter(prefix="/simulations", tags=["scenario simulator (demo)"])


class ScenarioInfo(Schema):
    key: str
    label: str
    kind: str
    description: str
    expected: str
    accounts_needed: int
    live: bool


class AccountScenarioCheck(Schema):
    key: str
    label: str
    kind: str
    expected: str
    accounts: int
    observed_levels: dict[str, int]
    passed: bool


class SimulationResult(Schema):
    scenario: str
    label: str
    accounts: list[dict[str, Any]]
    events: list[str]
    alerts: list[dict[str, Any]]
    verification_requests: list[str]
    synthetic: bool = True


@router.get("", response_model=list[ScenarioInfo], summary="Available synthetic scenarios")
def list_scenarios(_: Annotated[Principal, Depends(require(P.DASHBOARD_READ))]) -> list[ScenarioInfo]:
    return [
        ScenarioInfo(
            key=s.key,
            label=s.label,
            kind=s.kind,
            description=s.description,
            expected=s.expected,
            accounts_needed=s.accounts_needed,
            live=s.live,
        )
        for s in scenarios.SCENARIOS.values()
    ]


@router.get(
    "/validation",
    response_model=list[AccountScenarioCheck],
    summary="Checks each seeded account scenario against its expected risk level (coverage, not accuracy)",
)
def validation(
    db: DB, principal: Annotated[Principal, Depends(require(P.DASHBOARD_READ))]
) -> list[AccountScenarioCheck]:
    out = []
    for s in scenarios.SCENARIOS.values():
        levels = Counter(
            db.scalars(
                scoped(select(StudentFinancialAccount.risk_level), StudentFinancialAccount, principal).where(
                    StudentFinancialAccount.scenario_key == s.key
                )
            )
        )
        if not levels:
            continue
        out.append(
            AccountScenarioCheck(
                key=s.key,
                label=s.label,
                kind=s.kind,
                expected=s.expected,
                accounts=sum(levels.values()),
                observed_levels={k or "unassessed": v for k, v in levels.items()},
                passed=all(level in s.expected_levels for level in levels),
            )
        )
    return out


def _eligible(db: DB, principal: Principal, needed: int) -> list[StudentFinancialAccount]:
    acct = StudentFinancialAccount
    txn_count = select(func.count()).select_from(Transaction).where(Transaction.account_id == acct.id).scalar_subquery()
    has_card = (
        select(StudentIDCard.id)
        .where(StudentIDCard.account_id == acct.id, StudentIDCard.status == CardStatus.ACTIVE)
        .exists()
    )
    candidates = list(
        db.scalars(
            scoped(select(acct), acct, principal).where(
                acct.status == AccountStatus.ACTIVE,
                acct.sensitive_actions_restricted.is_(False),
                acct.study_mode == StudyMode.ON_CAMPUS,
                acct.scenario_key.is_(None),
                acct.risk_level == RiskLevel.LOW,
                txn_count >= 6,
                has_card,
            )
        )
    )
    by_org: dict[Any, list[StudentFinancialAccount]] = {}
    for a in candidates:
        by_org.setdefault(a.organization_id, []).append(a)
    pool = max(by_org.values(), key=len, default=[])
    if len(pool) < needed:
        raise ConflictError("Not enough untouched synthetic accounts left in this scope. Reset the demo data.")
    return random.sample(pool, needed)


@router.post(
    "/{key}",
    response_model=SimulationResult,
    status_code=201,
    summary="Play a scenario on synthetic accounts (DEMO_MODE only)",
)
def run(
    key: str,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.SIMULATIONS_RUN))],
) -> SimulationResult:
    if not get_settings().demo_mode:
        raise ForbiddenError("The scenario simulator is only available in demo mode.")
    scenario = scenarios.SCENARIOS.get(key)
    if scenario is None or not scenario.live:
        raise NotFoundError("Unknown live scenario.")
    chosen = _eligible(db, principal, scenario.accounts_needed)
    log = scenarios.play(db, key, chosen)
    ids = [a.id for a in chosen]
    alerts = db.scalars(select(Alert).where(Alert.account_id.in_(ids))).all()
    requests = db.scalars(select(VerificationRequest).where(VerificationRequest.account_id.in_(ids))).all()
    audit.record(
        db,
        category=AuditCategory.DETECTION,
        action="simulation.run",
        actor=principal.user,
        organization_id=chosen[0].organization_id,
        target_type="scenario",
        target_id=key,
        target_ref=key,
        details={"accounts": [a.reference for a in chosen], "synthetic": True},
        request=request,
    )
    db.commit()
    return SimulationResult(
        scenario=key,
        label=scenario.label,
        accounts=[
            {
                "id": str(a.id),
                "reference": a.reference,
                "risk_score": a.risk_score,
                "risk_level": a.risk_level,
                "status": a.status,
                "restricted": a.sensitive_actions_restricted,
            }
            for a in chosen
        ],
        events=log,
        alerts=[{"id": str(a.id), "reference": a.reference, "title": a.title, "severity": a.severity} for a in alerts],
        verification_requests=[r.reference for r in requests],
    )
