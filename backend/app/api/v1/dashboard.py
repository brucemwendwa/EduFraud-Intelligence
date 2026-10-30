"""Dashboard overview: portfolio metrics, trends and recent security activity — all from scoped records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require, scoped
from app.core.permissions import P
from app.db.types import utcnow
from app.models import (
    Alert,
    Disbursement,
    InvestigationCase,
    SecurityEvent,
    Student,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    VerificationRequest,
)
from app.models.enums import AccountStatus, CaseStatus, DisbursementStatus, SecurityEventType
from app.schemas.common import Schema
from app.services.alerts import LIVE_STATUSES
from app.services.verification_requests import OPEN_STATUSES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_E = SecurityEventType
_ELEVATED = ("medium", "high", "critical")
NOTABLE_EVENTS = {
    _E.NEW_DEVICE_LOGIN: "Account accessed from a new device",
    _E.PASSWORD_RESET_REQUESTED: "Password reset requested",
    _E.CARD_REPORTED_LOST: "Student ID card reported lost",
    _E.LOGIN_FAILED: "Failed authentication",
    _E.AID_REDIRECT_REQUESTED: "Request to redirect financial aid",
    _E.ACCOUNT_RECOVERY_REQUESTED: "Account recovery request",
    _E.MFA_FAILED: "Additional authentication failed",
    _E.CONTACT_DETAILS_CHANGED: "Recovery contact details changed",
    _E.ACCOUNT_RESTRICTED: "Sensitive actions restricted",
    _E.CARD_BLOCKED: "Card blocked at the provider",
}


class Metric(Schema):
    key: str
    label: str
    value: float
    link: str | None = None


class ActivityItem(Schema):
    kind: str  # "security_event" | "transaction"
    reference: str
    title: str
    detail: str
    student_ref: str
    account_id: str | None
    risk_level: str | None
    occurred_at: Any
    link: str


class DashboardOverview(Schema):
    synthetic: bool
    generated_at: Any
    metrics: list[Metric]
    allocation_trend: list[dict[str, Any]]
    transaction_activity: list[dict[str, Any]]
    risk_distribution: list[dict[str, Any]]
    suspicious_categories: list[dict[str, Any]]
    verification_outcomes: list[dict[str, Any]]
    investigation_status: list[dict[str, Any]]
    alert_status: list[dict[str, Any]]
    recent_activity: list[ActivityItem]


def _count(db: DB, principal: Principal, model: type, *where: Any) -> int:
    return db.scalar(scoped(select(func.count()).select_from(model), model, principal).where(*where)) or 0


@router.get("/overview", response_model=DashboardOverview, summary="Scoped portfolio metrics and trends")
def overview(db: DB, principal: Annotated[Principal, Depends(require(P.DASHBOARD_READ))]) -> DashboardOverview:
    now = utcnow()
    acct = StudentFinancialAccount
    allocated = db.scalar(
        scoped(select(func.coalesce(func.sum(Disbursement.amount), 0)), Disbursement, principal).where(
            Disbursement.status != DisbursementStatus.REVERSED
        )
    )
    metrics = [
        Metric(key="students", label="Students registered", value=_count(db, principal, Student)),
        Metric(
            key="active_accounts",
            label="Active ID-linked accounts",
            value=_count(db, principal, acct, acct.status == AccountStatus.ACTIVE),
            link="/app/accounts?status=active",
        ),
        Metric(
            key="aid_allocated", label="Financial aid allocated", value=float(allocated or 0), link="/app/disbursements"
        ),
        Metric(
            key="transactions",
            label="Transactions monitored",
            value=_count(db, principal, Transaction),
            link="/app/transactions",
        ),
        Metric(
            key="high_risk_alerts",
            label="High-risk security alerts",
            value=_count(
                db, principal, Alert, Alert.status.in_(LIVE_STATUSES), Alert.severity.in_(["high", "critical"])
            ),
            link="/app/alerts",
        ),
        Metric(
            key="suspicious_transactions",
            label="Suspicious transactions",
            value=_count(db, principal, Transaction, Transaction.risk_level.in_(["high", "critical"])),
            link="/app/transactions?flagged=true&sort=risk_score",
        ),
        Metric(
            key="verification_requests",
            label="Identity verification requests open",
            value=_count(db, principal, VerificationRequest, VerificationRequest.status.in_(OPEN_STATUSES)),
            link="/app/verification?tab=requests",
        ),
        Metric(
            key="open_cases",
            label="Open fraud investigations",
            value=_count(
                db,
                principal,
                InvestigationCase,
                InvestigationCase.status.not_in([CaseStatus.RESOLVED, CaseStatus.CLOSED]),
            ),
            link="/app/cases",
        ),
        Metric(
            key="cards_blocked",
            label="Blocked or reported ID cards",
            value=_count(
                db,
                principal,
                StudentIDCard,
                StudentIDCard.status.in_(["reported_lost", "blocked", "replacement_requested"]),
            ),
            link="/app/cards?status=blocked",
        ),
    ]

    # Allocation trend: weekly totals for the last 16 weeks (scheduled allocations shown separately).
    weeks: dict[date, dict[str, float]] = defaultdict(lambda: {"credited": 0.0, "scheduled": 0.0, "held": 0.0})
    start = (now - timedelta(weeks=15)).date()
    start -= timedelta(days=start.weekday())
    for when, amount, status in db.execute(
        scoped(select(Disbursement.disbursed_at, Disbursement.amount, Disbursement.status), Disbursement, principal)
    ):
        week = when.date() - timedelta(days=when.date().weekday())
        if week < start or week > now.date() + timedelta(days=42):
            continue
        bucket = (
            "held"
            if status == DisbursementStatus.HELD
            else ("scheduled" if status == DisbursementStatus.SCHEDULED else "credited")
        )
        weeks[week][bucket] += float(amount)
    allocation_trend = [{"week": w.isoformat(), **{k: round(v, 2) for k, v in weeks[w].items()}} for w in sorted(weeks)]

    # Transaction activity: daily counts for the last 30 days.
    since = now - timedelta(days=30)
    days: dict[str, dict[str, int]] = {
        (since + timedelta(days=i)).date().isoformat(): {"total": 0, "flagged": 0, "declined": 0} for i in range(31)
    }
    category_counts: Counter[str] = Counter()
    for when, level, status, indicators in db.execute(
        scoped(
            select(Transaction.occurred_at, Transaction.risk_level, Transaction.status, Transaction.risk_indicators),
            Transaction,
            principal,
        ).where(Transaction.occurred_at >= since)
    ):
        key = when.date().isoformat()
        if key in days:
            days[key]["total"] += 1
            days[key]["flagged"] += int(level in _ELEVATED)
            days[key]["declined"] += int(status == "declined")
        if level in _ELEVATED:
            for ind in indicators or []:
                category_counts[ind.get("title", ind.get("code", "Other"))] += 1
    transaction_activity = [{"date": d, **v} for d, v in days.items()]

    by_risk = dict(
        db.execute(scoped(select(acct.risk_level, func.count()).group_by(acct.risk_level), acct, principal)).all()
    )
    risk_distribution = [
        {"level": lvl, "accounts": by_risk.get(lvl, 0)} for lvl in ("low", "medium", "high", "critical")
    ]

    vr = dict(
        db.execute(
            scoped(
                select(VerificationRequest.status, func.count()).group_by(VerificationRequest.status),
                VerificationRequest,
                principal,
            )
        ).all()
    )
    cases = dict(
        db.execute(
            scoped(
                select(InvestigationCase.status, func.count()).group_by(InvestigationCase.status),
                InvestigationCase,
                principal,
            )
        ).all()
    )
    alerts = dict(db.execute(scoped(select(Alert.status, func.count()).group_by(Alert.status), Alert, principal)).all())

    events = db.scalars(
        scoped(select(SecurityEvent), SecurityEvent, principal)
        .where(SecurityEvent.event_type.in_(list(NOTABLE_EVENTS)))
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(60)
    ).all()
    activity: list[ActivityItem] = []
    seen: set[tuple[str, str]] = set()
    for e in events:  # collapse bursts (e.g. six failed sign-ins) into one line per account and type
        key = (str(e.student_id), e.event_type)
        if key in seen:
            continue
        seen.add(key)
        activity.append(
            ActivityItem(
                kind="security_event",
                reference=e.reference,
                title=NOTABLE_EVENTS[e.event_type],
                detail=f"{e.outcome.replace('_', ' ')} · {e.source.replace('_', ' ')}",
                student_ref=e.student.student_ref,
                account_id=str(e.account_id) if e.account_id else None,
                risk_level=e.risk_level,
                occurred_at=e.occurred_at,
                link=f"/app/access?selected={e.id}",
            )
        )
    for t in db.scalars(
        scoped(select(Transaction), Transaction, principal)
        .where(Transaction.risk_level.in_(["high", "critical"]))
        .order_by(Transaction.occurred_at.desc())
        .limit(8)
    ):
        top = (t.risk_indicators or [{}])[0].get("title", "Unusual transaction")
        activity.append(
            ActivityItem(
                kind="transaction",
                reference=t.reference,
                title=top,
                detail=f"{t.merchant_category.replace('_', ' ')} · ${Decimal(t.amount):,.2f} · {t.status}",
                student_ref=t.student.student_ref,
                account_id=str(t.account_id),
                risk_level=t.risk_level,
                occurred_at=t.occurred_at,
                link=f"/app/transactions?selected={t.id}",
            )
        )
    activity.sort(key=lambda a: a.occurred_at, reverse=True)
    synthetic = not db.scalar(
        scoped(select(func.count()).select_from(acct), acct, principal).where(acct.is_synthetic.is_(False))
    )
    return DashboardOverview(
        synthetic=synthetic,
        generated_at=now,
        metrics=metrics,
        allocation_trend=allocation_trend,
        transaction_activity=transaction_activity,
        risk_distribution=risk_distribution,
        suspicious_categories=[{"category": k, "count": v} for k, v in category_counts.most_common(7)],
        verification_outcomes=[{"status": k, "count": v} for k, v in sorted(vr.items())],
        investigation_status=[{"status": k, "count": v} for k, v in sorted(cases.items())],
        alert_status=[{"status": k, "count": v} for k, v in sorted(alerts.items())],
        recent_activity=activity[:14],
    )
