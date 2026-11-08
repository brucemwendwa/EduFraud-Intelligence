"""Dashboard overview: portfolio metrics, trends and recent security activity — all from scoped records."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require, scoped
from app.core.permissions import P
from app.db.types import utcnow
from app.models import (
    Alert,
    ApplicationDocument,
    ApplicationStatusHistory,
    Disbursement,
    FinancialAidApplication,
    InvestigationCase,
    SecurityEvent,
    Student,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    VerificationRequest,
)
from app.models.enums import (
    AccountStatus,
    ApplicationStatus,
    CaseStatus,
    DisbursementStatus,
    DocumentReviewStatus,
    DocumentStatus,
    SecurityEventType,
)
from app.schemas.common import Schema
from app.services.alerts import LIVE_STATUSES
from app.services.application_lifecycle import AWAITING_REVIEW, OPEN_FOR_REVIEW
from app.services.verification_requests import OPEN_STATUSES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_RECENT_APPLICATION_EVENTS = 12
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


class RiskCount(Schema):
    level: str
    count: int


class ApplicationActivity(Schema):
    application_id: str
    reference: str
    student_ref: str
    from_status: str | None
    to_status: str
    actor_role: str | None
    risk_level: str | None
    occurred_at: datetime


class ApplicationPipeline(Schema):
    generated_at: datetime
    total: int
    awaiting_review: int
    in_review: int
    additional_information_required: int
    on_hold: int
    approved: int
    rejected: int
    withdrawn: int
    open_total: int
    open_by_risk: list[RiskCount]
    open_unassessed: int
    documents_awaiting_review: int
    recent_activity: list[ApplicationActivity]


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


@router.get("/applications", response_model=ApplicationPipeline, summary="Scoped aid application pipeline")
def application_pipeline(
    db: DB, principal: Annotated[Principal, Depends(require(P.APPLICATIONS_READ))]
) -> ApplicationPipeline:
    """Application-processing figures only. Unsubmitted drafts belong to the student and are never counted."""
    app = FinancialAidApplication
    submitted = app.submitted_at.is_not(None)
    by_status: Counter[str] = Counter(
        dict(
            db.execute(
                scoped(select(app.status, func.count()).where(submitted).group_by(app.status), app, principal)
            ).all()
        )
    )
    open_values = [s.value for s in OPEN_FOR_REVIEW]
    open_risk: Counter[str | None] = Counter(
        dict(
            db.execute(
                scoped(
                    select(app.risk_level, func.count())
                    .where(submitted, app.status.in_(open_values))
                    .group_by(app.risk_level),
                    app,
                    principal,
                )
            ).all()
        )
    )
    documents_awaiting_review = (
        db.scalar(
            scoped(
                select(func.count())
                .select_from(ApplicationDocument)
                .join(app, app.id == ApplicationDocument.application_id)
                .where(
                    submitted,
                    ApplicationDocument.status == DocumentStatus.AVAILABLE,
                    ApplicationDocument.review_status == DocumentReviewStatus.PENDING,
                ),
                ApplicationDocument,
                principal,
            )
        )
        or 0
    )

    # Status changes first; records that predate lifecycle history fill the list by submission time.
    history = ApplicationStatusHistory
    rows = db.execute(
        scoped(
            select(history, app)
            .join(app, app.id == history.application_id)
            .where(
                submitted,
                history.from_status.is_distinct_from(history.to_status),
                history.to_status != ApplicationStatus.DRAFT,
            )
            .order_by(history.created_at.desc())
            .limit(_RECENT_APPLICATION_EVENTS),
            history,
            principal,
        )
    ).all()
    activity = [
        ApplicationActivity(
            application_id=str(a.id),
            reference=a.reference,
            student_ref=a.student.student_ref,
            from_status=h.from_status,
            to_status=h.to_status,
            actor_role=h.actor_role,
            risk_level=a.risk_level,
            occurred_at=h.created_at,
        )
        for h, a in rows
    ]
    if len(activity) < _RECENT_APPLICATION_EVENTS:
        seen = {item.application_id for item in activity}
        for a in db.scalars(
            scoped(select(app).where(submitted), app, principal)
            .order_by(app.submitted_at.desc())
            .limit(_RECENT_APPLICATION_EVENTS)
        ):
            if str(a.id) not in seen and len(activity) < _RECENT_APPLICATION_EVENTS:
                activity.append(
                    ApplicationActivity(
                        application_id=str(a.id),
                        reference=a.reference,
                        student_ref=a.student.student_ref,
                        from_status=None,
                        to_status=a.status,
                        actor_role=None,
                        risk_level=a.risk_level,
                        occurred_at=a.submitted_at,
                    )
                )

    return ApplicationPipeline(
        generated_at=utcnow(),
        total=sum(by_status.values()),
        awaiting_review=sum(by_status[s.value] for s in AWAITING_REVIEW),
        in_review=by_status[ApplicationStatus.IN_REVIEW.value],
        additional_information_required=by_status[ApplicationStatus.ADDITIONAL_INFORMATION_REQUIRED.value],
        on_hold=by_status[ApplicationStatus.ON_HOLD.value],
        approved=by_status[ApplicationStatus.APPROVED.value],
        rejected=by_status[ApplicationStatus.REJECTED.value],
        withdrawn=by_status[ApplicationStatus.WITHDRAWN.value],
        open_total=sum(by_status[v] for v in open_values),
        open_by_risk=[RiskCount(level=lvl, count=open_risk[lvl]) for lvl in ("critical", "high", "medium", "low")],
        open_unassessed=open_risk[None],
        documents_awaiting_review=documents_awaiting_review,
        recent_activity=activity,
    )
