"""Account-protection risk engine for student ID-linked financial aid accounts.

Combines authorised provider events — card transactions, sign-ins, credential and recovery
changes, card reports and aid-redirection requests — with relationship analysis into one
explainable assessment per account, using the same noisy-OR scoring and score bands as the
application engine (app.detection.signals).

Design rules:
  * No single weak signal escalates: a new device, a trip or a quiet month stays low on its own.
  * Locations are coarse (city/country) and come only from authorised transaction and sign-in
    events; there is no continuous tracking. Signal text and evidence never name a location.
  * Lack of spending is context only (near-zero weight).
  * Scores are prioritisation aids. The engine never declares fraud; people decide.
"""

from __future__ import annotations

import statistics
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.detection.account_rules import (
    ACCOUNT_ENGINE_METHOD,
    ACCOUNT_RULES_VERSION,
    HIGH_RISK_MERCHANT_CATEGORIES,
    TAKEOVER_FAMILY,
    rule,
)
from app.detection.signals import Signal, combine, dedupe, explain, level_for
from app.models import (
    Device,
    Disbursement,
    FraudSignal,
    IdentityVerification,
    RiskAssessment,
    SecurityEvent,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    User,
    VerificationRequest,
)
from app.models.enums import (
    DeviceTrust,
    RiskLevel,
    SecurityEventType,
    TransactionStatus,
    VerificationOutcome,
    VerificationRequestStatus,
)

HISTORY_DAYS = 90
WINDOW_DAYS = 30
_E = SecurityEventType
RECOVERY_EVENTS = frozenset({_E.PASSWORD_RESET_REQUESTED, _E.PASSWORD_CHANGED, _E.ACCOUNT_RECOVERY_REQUESTED})
CREDENTIAL_EVENTS = RECOVERY_EVENTS | {_E.CONTACT_DETAILS_CHANGED, _E.MFA_FAILED}
LOGIN_EVENTS = frozenset({_E.LOGIN_SUCCESS, _E.NEW_DEVICE_LOGIN, _E.LOGIN_FAILED})
PHYSICAL_CHANNELS = frozenset({"card_present", "atm"})

RECOMMENDATIONS = {
    RiskLevel.LOW: "No action needed. Continue routine monitoring.",
    RiskLevel.MEDIUM: "Ask for additional authentication before sensitive changes and review the listed signals.",
    RiskLevel.HIGH: (
        "Human review required. Hold sensitive account changes and request identity re-verification "
        "through the student's pathway."
    ),
    RiskLevel.CRITICAL: (
        "Keep sensitive actions on hold, contact the student through a known-good channel and open an "
        "investigation. No adverse action may be taken without human review."
    ),
}
CATEGORY_ADVICE = {
    "card_security": "Confirm the card is blocked at the provider; replace it only after verification.",
    "aid_redirection": "Do not apply any payout change until the student's identity is verified.",
    "network": "Review the linked accounts in Fraud Network Intelligence before acting on any one of them.",
}


@dataclass
class AccountEvaluation:
    score: float
    level: RiskLevel
    signals: list[Signal]
    explanation: str
    recommendation: str
    categories: set[str]
    takeover_indicators: bool
    riskiest_transaction: Transaction | None = None
    latest_event: SecurityEvent | None = None
    features: dict[str, float] = field(default_factory=dict)

    @property
    def needs_protection(self) -> bool:
        """High combined risk from at least two independent categories, one of them account takeover."""
        return (
            self.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
            and self.takeover_indicators
            and len(self.categories) >= 2
        )


def _signal(
    code: str, *, evidence: dict, scale: float = 1.0, title: str | None = None, description: str | None = None
) -> Signal | None:
    r = rule(code)
    weight = round(r.weight * scale, 3)
    if weight <= 0:
        return None
    return Signal(
        code=r.code,
        category=r.category,
        severity=r.severity,
        weight=weight,
        title=title or r.title,
        description=description or r.description,
        method="relationship" if r.category == "network" else "rule",
        version=ACCOUNT_RULES_VERSION,
        evidence=evidence,
    )


@dataclass
class AccountSnapshot:
    """Everything the rules need about one account, loaded once."""

    account: StudentFinancialAccount
    now: datetime
    transactions: list[Transaction]
    events: list[SecurityEvent]
    devices: dict[uuid.UUID, Device]
    cards: dict[uuid.UUID, StudentIDCard]
    requests: list[VerificationRequest]
    failed_verifications: list[IdentityVerification]
    device_reach: dict[str, tuple[int, int]]  # device token -> (students in org, students elsewhere)
    destination_reach: dict[uuid.UUID, tuple[int, int]]

    def device_of(self, event: SecurityEvent) -> Device | None:
        return self.devices.get(event.device_id) if event.device_id else None

    def trusted(self, event: SecurityEvent) -> bool:
        device = self.device_of(event)
        return device is not None and device.trust_status == DeviceTrust.TRUSTED

    def known_countries(self, before: datetime) -> set[str]:
        seen = [t.location_country for t in self.transactions if t.occurred_at < before and t.location_country]
        return {self.account.home_country} | {c for c in seen if seen.count(c) >= 2}


def load_snapshot(db: Session, account: StudentFinancialAccount, now: datetime | None = None) -> AccountSnapshot:
    now = now or utcnow()
    student_id = account.student_id
    txns = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id, Transaction.occurred_at >= now - timedelta(days=HISTORY_DAYS))
            .where(Transaction.occurred_at <= now)
            .order_by(Transaction.occurred_at)
        )
    )
    events = list(
        db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.student_id == student_id,
                SecurityEvent.occurred_at >= now - timedelta(days=WINDOW_DAYS),
                SecurityEvent.occurred_at <= now,
            )
            .order_by(SecurityEvent.occurred_at)
        )
    )
    devices = {d.id: d for d in db.scalars(select(Device).where(Device.student_id == student_id))}
    cards = {c.id: c for c in db.scalars(select(StudentIDCard).where(StudentIDCard.student_id == student_id))}
    requests = list(
        db.scalars(
            select(VerificationRequest)
            .where(VerificationRequest.student_id == student_id)
            .order_by(VerificationRequest.created_at)
        )
    )
    failed = list(
        db.scalars(
            select(IdentityVerification).where(
                IdentityVerification.student_id == student_id,
                IdentityVerification.status == VerificationOutcome.FAILED,
                IdentityVerification.created_at >= now - timedelta(days=WINDOW_DAYS),
            )
        )
    )
    return AccountSnapshot(
        account=account,
        now=now,
        transactions=txns,
        events=events,
        devices=devices,
        cards=cards,
        requests=requests,
        failed_verifications=failed,
        device_reach=_device_reach(db, account, [d.device_token for d in devices.values()], now),
        destination_reach=_destination_reach(
            db,
            account,
            {e.destination_id for e in events if e.destination_id}
            | {t.destination_id for t in txns if t.destination_id},
        ),
    )


def _split(rows: Iterable[tuple[uuid.UUID, uuid.UUID]], account: StudentFinancialAccount) -> tuple[int, int]:
    students: dict[uuid.UUID, uuid.UUID] = dict(rows)
    students.pop(account.student_id, None)
    same = sum(1 for org in students.values() if org == account.organization_id)
    return same, len(students) - same


def _device_reach(
    db: Session, account: StudentFinancialAccount, tokens: list[str], now: datetime
) -> dict[str, tuple[int, int]]:
    """Other students (platform-wide, counts only) whose accounts this device signed in to recently."""
    if not tokens:
        return {}
    rows = db.execute(
        select(Device.device_token, Device.student_id, Device.organization_id).where(
            Device.device_token.in_(tokens),
            Device.is_shared_kiosk.is_(False),
            Device.last_seen_at >= now - timedelta(days=WINDOW_DAYS),
        )
    ).all()
    out: dict[str, tuple[int, int]] = {}
    for token in tokens:
        out[token] = _split(((s, o) for t, s, o in rows if t == token), account)
    return out


def _destination_reach(
    db: Session, account: StudentFinancialAccount, destination_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[int, int]]:
    """Other students (counts only) linked to the same payout or transfer destination."""
    if not destination_ids:
        return {}
    pairs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
    for model in (SecurityEvent, Transaction, Disbursement):
        pairs += db.execute(
            select(model.destination_id, model.student_id, model.organization_id)  # type: ignore[attr-defined]
            .where(model.destination_id.in_(destination_ids))  # type: ignore[attr-defined]
            .distinct()
        ).all()
    return {d: _split(((s, o) for dest, s, o in pairs if dest == d), account) for d in destination_ids}


# ---------------------------------------------------------------- transaction rules


def is_suspicious_auth(snap: AccountSnapshot, event: SecurityEvent) -> bool:
    if snap.trusted(event):
        return False
    if event.event_type in CREDENTIAL_EVENTS or event.event_type == _E.AID_REDIRECT_REQUESTED:
        return True
    if event.event_type == _E.NEW_DEVICE_LOGIN and event.location_country:
        return event.location_country not in snap.known_countries(event.occurred_at)
    return False


def transaction_signals(snap: AccountSnapshot, txn: Transaction) -> list[Signal]:
    """Signals for one transaction, judged against the history that preceded it."""
    prior = [t for t in snap.transactions if t.occurred_at < txn.occurred_at and t.id != txn.id]
    approved = [t for t in prior if t.status == TransactionStatus.APPROVED]
    ref = {"transaction": txn.reference}
    out: list[Signal | None] = []

    card = snap.cards.get(txn.card_id) if txn.card_id else None
    lost_at = card and (card.reported_lost_at or card.blocked_at)
    if lost_at and txn.occurred_at >= lost_at:
        hours = (txn.occurred_at - lost_at).total_seconds() / 3600
        out.append(
            _signal(
                "TXN_AFTER_CARD_LOST",
                evidence={**ref, "card": card.reference, "hours_after_report": round(hours, 1)},  # type: ignore[union-attr]
                description=f"The card was used {hours:.1f} hours after it was reported lost or blocked; "
                "the provider declined the authorisation.",
            )
        )

    physical = txn.channel in PHYSICAL_CHANNELS and txn.location_country
    if physical:
        known = snap.known_countries(txn.occurred_at)
        cities = [t.location_city for t in approved if t.channel in PHYSICAL_CHANNELS and t.location_city]
        known_cities = {snap.account.home_city} | {c for c in cities if cities.count(c) >= 2}
        if txn.location_country not in known:
            out.append(
                _signal(
                    "UNUSUAL_LOCATION",
                    evidence={**ref, "scope": "country"},
                    description="Card-present transaction in a country not seen in this student's "
                    "activity. Students travel; review together with other signals.",
                )
            )
        elif len(cities) >= 5 and txn.location_city not in known_cities:
            out.append(
                _signal(
                    "UNUSUAL_LOCATION",
                    scale=0.6,
                    evidence={**ref, "scope": "city"},
                    title="Transaction in a new city",
                    description="Card-present transaction in a city outside this student's usual "
                    "pattern (same country). Often travel; low weight on its own.",
                )
            )
        recent = [
            t
            for t in prior
            if t.channel in PHYSICAL_CHANNELS
            and t.location_country
            and txn.occurred_at - t.occurred_at <= timedelta(hours=6)
        ]
        elsewhere = [t for t in recent if t.location_country != txn.location_country]
        if elsewhere:
            gap = (txn.occurred_at - elsewhere[-1].occurred_at).total_seconds() / 3600
            out.append(
                _signal(
                    "IMPOSSIBLE_TRAVEL",
                    evidence={**ref, "previous": elsewhere[-1].reference, "hours_apart": round(gap, 1)},
                    description=f"Card-present transactions in two different countries {gap:.1f} hours "
                    "apart — too close together to travel between.",
                )
            )

    amounts = [float(t.amount) for t in approved if t.transaction_type != "transfer_out"]
    amount = float(txn.amount)
    if len(amounts) >= 5:
        typical = statistics.median(amounts)
        if amount >= max(300.0, 4 * typical):
            out.append(
                _signal(
                    "SPENDING_SPIKE",
                    evidence={**ref, "amount": amount, "typical": round(typical, 2)},
                    description=f"${amount:,.0f} is {amount / typical:.0f}x this student's typical "
                    f"transaction (${typical:,.0f}).",
                )
            )
    elif amount >= 1000:
        out.append(
            _signal(
                "SPENDING_SPIKE",
                scale=0.6,
                evidence={**ref, "amount": amount},
                description=f"${amount:,.0f} with little prior history to compare against.",
            )
        )

    if txn.merchant_category in HIGH_RISK_MERCHANT_CATEGORIES and not any(
        t.merchant_category == txn.merchant_category for t in approved
    ):
        out.append(
            _signal(
                "HIGH_RISK_CATEGORY_NEW",
                evidence={**ref, "category": txn.merchant_category},
                description=f"First {txn.merchant_category.replace('_', ' ')} transaction on this account.",
            )
        )

    window = [t for t in prior if txn.occurred_at - t.occurred_at <= timedelta(minutes=30)]
    risky = [
        t
        for t in prior
        if t.merchant_category in HIGH_RISK_MERCHANT_CATEGORIES
        and txn.occurred_at - t.occurred_at <= timedelta(hours=1)
    ]
    if len(window) + 1 >= 4 or (txn.merchant_category in HIGH_RISK_MERCHANT_CATEGORIES and len(risky) + 1 >= 3):
        out.append(_signal("RAPID_SEQUENCE", evidence={**ref, "transactions_in_window": len(window) + 1}))

    suspicious = [
        e
        for e in snap.events
        if e.occurred_at <= txn.occurred_at
        and txn.occurred_at - e.occurred_at <= timedelta(hours=6)
        and is_suspicious_auth(snap, e)
    ]
    if suspicious:
        last = suspicious[-1]
        hours = (txn.occurred_at - last.occurred_at).total_seconds() / 3600
        out.append(
            _signal(
                "TXN_AFTER_SUSPICIOUS_AUTH",
                evidence={**ref, "event": last.reference, "hours_after": round(hours, 1)},
                description=f"Transaction {hours:.1f} hours after "
                f"{last.event_type.replace('_', ' ')} from an unconfirmed session.",
            )
        )

    if txn.destination_id:
        same, other = snap.destination_reach.get(txn.destination_id, (0, 0))
        if same + other >= 2:
            out.append(
                _signal(
                    "DESTINATION_SHARED_ACCOUNTS",
                    evidence={**ref, "students_in_scope": same, "students_other_institutions": other},
                    description=f"Transfer destination also linked to {same + other} other students "
                    f"({other} at other institutions; details not shared).",
                )
            )
    return [s for s in out if s is not None]


def score_transaction(snap: AccountSnapshot, txn: Transaction) -> list[Signal]:
    """Scores and annotates a transaction in place. Returns its signals."""
    signals = dedupe(transaction_signals(snap, txn))
    score = combine(signals)
    txn.risk_score = score
    txn.risk_level = level_for(score)
    txn.risk_indicators = [
        {"code": s.code, "title": s.title, "category": s.category, "points": s.points, "description": s.description}
        for s in signals
    ]
    return signals


# ---------------------------------------------------------------- account rules


def _burst(events: list[SecurityEvent], size: int, span: timedelta) -> list[SecurityEvent] | None:
    for i in range(len(events) - size + 1):
        if events[i + size - 1].occurred_at - events[i].occurred_at <= span:
            return events[i : i + size]
    return None


def account_signals(snap: AccountSnapshot) -> tuple[list[Signal], Transaction | None, SecurityEvent | None]:
    acct, now = snap.account, snap.now
    out: list[Signal | None] = []
    recent = [e for e in snap.events if now - e.occurred_at <= timedelta(days=7)]
    notable: list[SecurityEvent] = []

    # Identity
    failed_requests = [
        r
        for r in snap.requests
        if r.status == VerificationRequestStatus.FAILED
        and r.decided_at
        and now - r.decided_at <= timedelta(days=WINDOW_DAYS)
    ]
    if failed_requests or snap.failed_verifications:
        refs = [r.reference for r in failed_requests] + [v.reference for v in snap.failed_verifications]
        out.append(_signal("IDV_FAILED_RECENT", evidence={"verifications": refs[:4]}))

    # Device
    unconfirmed = [
        e
        for e in snap.events
        if e.event_type == _E.NEW_DEVICE_LOGIN
        and now - e.occurred_at <= timedelta(days=14)
        and (d := snap.device_of(e)) is not None
        and d.trust_status != DeviceTrust.TRUSTED
    ]
    if unconfirmed:
        notable.append(unconfirmed[-1])
        out.append(
            _signal(
                "NEW_DEVICE",
                evidence={"event": unconfirmed[-1].reference, "device": snap.device_of(unconfirmed[-1]).label},
            )
        )  # type: ignore[union-attr]
    flagged = [d for d in snap.devices.values() if d.trust_status == DeviceTrust.SUSPICIOUS]
    if flagged:
        out.append(_signal("DEVICE_FLAGGED", evidence={"devices": [d.label for d in flagged][:3]}))

    # Authentication
    failures = [e for e in recent if e.event_type == _E.LOGIN_FAILED]
    burst = _burst(failures, 5, timedelta(hours=1))
    if burst:
        notable.append(burst[-1])
        out.append(
            _signal(
                "FAILED_LOGIN_BURST",
                evidence={"failed_attempts": len(failures), "first": burst[0].reference},
                description=f"{len(failures)} failed sign-ins in the last 7 days, including five within one hour.",
            )
        )
    mfa_failed = [e for e in recent if e.event_type == _E.MFA_FAILED]
    if mfa_failed:
        notable.append(mfa_failed[-1])
        out.append(_signal("MFA_FAILED", evidence={"event": mfa_failed[-1].reference, "count": len(mfa_failed)}))
    odd_logins = [
        e
        for e in recent
        if e.event_type in (_E.LOGIN_SUCCESS, _E.NEW_DEVICE_LOGIN, _E.LOGIN_FAILED)
        and e.location_country
        and e.location_country not in snap.known_countries(e.occurred_at)
        and not snap.trusted(e)
    ]
    if odd_logins:
        out.append(_signal("UNUSUAL_LOGIN_LOCATION", evidence={"event": odd_logins[-1].reference}))

    # Account recovery
    recovery = [e for e in recent if e.event_type in RECOVERY_EVENTS]
    unfamiliar_recovery = [e for e in recovery if not snap.trusted(e)]
    if unfamiliar_recovery:
        notable.append(unfamiliar_recovery[-1])
        out.append(_signal("PASSWORD_RESET_UNFAMILIAR", evidence={"event": unfamiliar_recovery[-1].reference}))
    requests = [e for e in recovery if e.event_type != _E.PASSWORD_CHANGED]
    if len(requests) >= 2:
        out.append(
            _signal(
                "RECOVERY_REPEATED",
                evidence={"requests": len(requests)},
                description=f"{len(requests)} password-reset or recovery requests in seven days.",
            )
        )
    contact = [
        e
        for e in recent
        if e.event_type == _E.CONTACT_DETAILS_CHANGED
        and not snap.trusted(e)
        and any(r.occurred_at <= e.occurred_at <= r.occurred_at + timedelta(hours=48) for r in recovery)
    ]
    if contact:
        notable.append(contact[-1])
        out.append(_signal("CONTACT_CHANGE_AFTER_RESET", evidence={"event": contact[-1].reference}))

    # Aid redirection
    redirects = [e for e in snap.events if e.event_type == _E.AID_REDIRECT_REQUESTED and not snap.trusted(e)]
    if redirects:
        notable.append(redirects[-1])
        out.append(
            _signal(
                "AID_REDIRECT_ATTEMPT", evidence={"event": redirects[-1].reference, "outcome": redirects[-1].outcome}
            )
        )
        for e in redirects:
            same, other = snap.destination_reach.get(e.destination_id, (0, 0)) if e.destination_id else (0, 0)
            if same + other >= 2:
                out.append(
                    _signal(
                        "DESTINATION_SHARED_ACCOUNTS",
                        evidence={
                            "event": e.reference,
                            "students_in_scope": same,
                            "students_other_institutions": other,
                        },
                        description=f"The requested payout destination is already linked to {same + other} "
                        f"other students ({other} at other institutions; details not shared).",
                    )
                )
                break

    # Card security
    for card in snap.cards.values():
        if card.reported_lost_at and now - card.reported_lost_at <= timedelta(days=14):
            out.append(_signal("CARD_REPORTED_LOST", evidence={"card": card.reference}))
            if card.replacement_requested_at and not any(
                r.status == VerificationRequestStatus.VERIFIED
                and r.decided_at
                and r.decided_at >= card.reported_lost_at
                for r in snap.requests
            ):
                out.append(_signal("REPLACEMENT_UNVERIFIED", evidence={"card": card.reference}))

    # Network: one device across several students' accounts
    for device in snap.devices.values():
        if device.is_shared_kiosk or now - device.last_seen_at > timedelta(days=WINDOW_DAYS):
            continue
        same, other = snap.device_reach.get(device.device_token, (0, 0))
        if same + other >= 2:
            out.append(
                _signal(
                    "DEVICE_SHARED_ACCOUNTS",
                    evidence={"device": device.label, "students_in_scope": same, "students_other_institutions": other},
                    description=f"A device used on this account also signed in to {same + other} other "
                    f"student accounts ({other} at other institutions; details not shared).",
                )
            )
            break

    # Transactions in the window (each judged against its own history)
    window = [t for t in snap.transactions if now - t.occurred_at <= timedelta(days=WINDOW_DAYS)]
    riskiest: Transaction | None = None
    best = 0.0
    for txn in window:
        txn_signals = transaction_signals(snap, txn)
        out.extend(txn_signals)
        score = combine(dedupe(list(txn_signals)))
        if score > best:
            riskiest, best = txn, score

    # Context: no spending near campus (on-campus students only; never weighs more than 2 points)
    if (
        acct.study_mode == "on_campus"
        and now - acct.opened_at > timedelta(days=WINDOW_DAYS)
        and not any(t.channel in PHYSICAL_CHANNELS and t.location_city == acct.home_city for t in window)
    ):
        out.append(_signal("NO_LOCAL_ACTIVITY", evidence={"days": WINDOW_DAYS}))

    latest = max(notable, key=lambda e: e.occurred_at) if notable else None
    return [s for s in out if s is not None], riskiest if best >= 30 else None, latest


def evaluate(snap: AccountSnapshot) -> AccountEvaluation:
    raw, riskiest, latest = account_signals(snap)
    signals = dedupe(raw)
    score = combine(signals)
    level = level_for(score)
    contributing = {s.category for s in signals if not rule(s.code).context_only}
    recommendation = RECOMMENDATIONS[level]
    if level != RiskLevel.LOW:
        extra = [CATEGORY_ADVICE[c] for c in ("card_security", "aid_redirection", "network") if c in contributing]
        recommendation = " ".join([recommendation, *extra])
    return AccountEvaluation(
        score=score,
        level=level,
        signals=signals,
        explanation=explain(score, level, signals),
        recommendation=recommendation[:300],
        categories=contributing,
        takeover_indicators=bool(contributing & TAKEOVER_FAMILY),
        riskiest_transaction=riskiest,
        latest_event=latest,
        features={
            "transactions_90d": float(len(snap.transactions)),
            "security_events_30d": float(len(snap.events)),
            "devices": float(len(snap.devices)),
        },
    )


def persist(
    db: Session,
    account: StudentFinancialAccount,
    result: AccountEvaluation,
    *,
    triggered_by: str,
    user: User | None = None,
    at: datetime | None = None,
) -> tuple[RiskAssessment, bool]:
    """Stores the assessment (a new version only when it changed). Returns (current assessment, changed)."""
    at = at or utcnow()
    current = db.scalar(
        select(RiskAssessment).where(RiskAssessment.account_id == account.id, RiskAssessment.is_current)
    )
    account.risk_score, account.risk_level, account.last_assessed_at = result.score, result.level, at
    if (
        current is not None
        and abs(current.score - result.score) < 0.5
        and sorted(s.code for s in current.signals) == sorted(s.code for s in result.signals)
    ):
        return current, False
    if current is not None:
        current.is_current = False
    assessment = RiskAssessment(
        organization_id=account.organization_id,
        subject_type="account",
        account_id=account.id,
        score=result.score,
        level=result.level,
        method=ACCOUNT_ENGINE_METHOD,
        rules_version=ACCOUNT_RULES_VERSION,
        model_version=None,
        explanation=result.explanation,
        recommended_action=result.recommendation,
        feature_snapshot=result.features,
        triggered_by=triggered_by,
        triggered_by_user_id=user.id if user else None,
        is_current=True,
        created_at=at,
    )
    assessment.signals = [
        FraudSignal(
            organization_id=account.organization_id,
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
            created_at=at,
        )
        for s in result.signals
    ]
    db.add(assessment)
    db.flush()
    return assessment, True


def spent_total(db: Session, account_id: uuid.UUID) -> Decimal:
    return db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == account_id, Transaction.status == TransactionStatus.APPROVED
        )
    ) or Decimal("0")
