"""Synthetic demonstration scenarios for student ID-linked accounts.

Each scenario replays a realistic sequence of provider events through the *real* ingestion,
card and verification services, so what the demo shows is exactly what the platform does with
live events. Used by the seed pipeline (historical timeline) and by the live scenario simulator
(demo mode only). All identifiers are synthetic and generated in memory.

Fraud scenarios should end high or critical (password reset: medium, with step-up requested);
legitimate controls must stay low — the system should not flag every unusual event.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import StudentFinancialAccount, StudentIDCard
from app.models.enums import CardStatus, SecurityEventType
from app.services import accounts, cards
from app.services.account_events import ingest_security_event, ingest_transaction

_E = SecurityEventType


@dataclass
class PlayContext:
    db: Session
    accounts: list[StudentFinancialAccount]
    start: datetime
    rng: random.Random
    key: str
    log: list[str] = field(default_factory=list)

    def at(self, minutes: float) -> datetime:
        return self.start + timedelta(minutes=minutes)

    def raw(self, prefix: str) -> str:
        return f"sim-{prefix}-{self.rng.getrandbits(48):012x}"

    def event_id(self) -> str:
        return f"sbx-evt-{self.rng.getrandbits(64):016x}"

    def card(self, account: StudentFinancialAccount) -> StudentIDCard | None:
        return self.db.scalar(
            select(StudentIDCard).where(
                StudentIDCard.account_id == account.id, StudentIDCard.status == CardStatus.ACTIVE
            )
        )

    def security(self, account: StudentFinancialAccount, event_type: str, minutes: float, **kw: object) -> None:
        event, decision = ingest_security_event(
            self.db,
            account,
            event_type=event_type,
            occurred_at=self.at(minutes),
            provider_event_id=self.event_id(),
            scenario_key=self.key,
            **kw,  # type: ignore[arg-type]
        )
        self.log.append(f"{event.reference} {event.event_type} → {decision.decision}")

    def purchase(
        self,
        account: StudentFinancialAccount,
        minutes: float,
        *,
        merchant: str,
        category: str,
        amount: str,
        city: str | None,
        country: str | None,
        channel: str = "card_present",
        transaction_type: str = "purchase",
        card: StudentIDCard | None = None,
        destination_raw: str | None = None,
    ) -> None:
        txn = ingest_transaction(
            self.db,
            account,
            provider_event_id=self.event_id(),
            amount=Decimal(amount),
            merchant_name=merchant,
            merchant_category=category,
            merchant_raw=merchant,
            occurred_at=self.at(minutes),
            channel=channel,
            transaction_type=transaction_type,
            card=card or self.card(account),
            city=city,
            country=country,
            destination_raw=destination_raw,
            scenario_key=self.key,
        )
        self.log.append(f"{txn.reference} {txn.merchant_category} ${txn.amount} → {txn.status}")


# ---------------------------------------------------------------- fraud scenarios


def lost_card(p: PlayContext) -> None:
    acct = p.accounts[0]
    card = p.card(acct)
    if card is None:
        raise ValueError("Scenario needs an account with an active card.")
    req = cards.report_lost(
        p.db,
        card,
        channel="student_portal",
        note="Student reports the ID card missing after a lecture.",
        actor=None,
        at=p.at(0),
        scenario_key=p.key,
    )
    p.log.append(f"{card.reference} reported lost, blocked at provider; {req.reference} opened")
    p.purchase(
        acct,
        135,
        merchant="TechHub Electronics",
        category="electronics",
        amount="649.00",
        city="Columbus",
        country="US",
        card=card,
    )


def password_reset(p: PlayContext) -> None:
    acct = p.accounts[0]
    device, ip = p.raw("device"), p.raw("ip")
    common = {
        "device_raw": device,
        "device_label": "Unrecognised Windows PC · Chrome",
        "platform": "windows",
        "ip_raw": ip,
        "city": "Rotterdam",
        "country": "NL",
        "session_raw": p.raw("session"),
    }
    for i in range(3):
        p.security(acct, _E.LOGIN_FAILED, i, outcome="failure", **common)
    p.security(acct, _E.PASSWORD_RESET_REQUESTED, 5, outcome="challenged", **common)
    p.security(acct, _E.MFA_FAILED, 6, outcome="failure", **common)


def account_takeover(p: PlayContext) -> None:
    acct = p.accounts[0]
    common = {
        "device_raw": p.raw("device"),
        "device_label": "Unrecognised Android phone",
        "platform": "android",
        "ip_raw": p.raw("ip"),
        "city": "Lisbon",
        "country": "PT",
        "session_raw": p.raw("session"),
    }
    for i in range(6):
        p.security(acct, _E.LOGIN_FAILED, i * 3, outcome="failure", **common)
    p.security(acct, _E.LOGIN_SUCCESS, 25, outcome="success", **common)
    p.security(acct, _E.PASSWORD_RESET_REQUESTED, 30, outcome="success", **common)
    p.security(acct, _E.PASSWORD_CHANGED, 33, outcome="success", **common)
    p.security(acct, _E.CONTACT_DETAILS_CHANGED, 40, outcome="success", details={"field": "recovery_email"}, **common)
    destination = "0990" + str(p.rng.randint(10**10, 10**11 - 1)) + "77"
    p.security(acct, _E.AID_REDIRECT_REQUESTED, 48, outcome="requested", destination_raw=destination, **common)
    p.purchase(
        acct,
        55,
        merchant="SendFast Transfers",
        category="money_transfer",
        amount="1900.00",
        city=None,
        country=None,
        channel="transfer",
        transaction_type="transfer_out",
        destination_raw=destination,
    )
    p.purchase(
        acct,
        62,
        merchant="GiftCard Depot",
        category="gift_cards",
        amount="500.00",
        city=None,
        country=None,
        channel="online",
    )


def suspicious_transaction(p: PlayContext) -> None:
    acct = p.accounts[0]
    p.purchase(
        acct,
        0,
        merchant="Cardinal Coffee",
        category="dining",
        amount="4.75",
        city=acct.home_city,
        country=acct.home_country,
    )
    p.purchase(
        acct, 125, merchant="TechHub Electronics", category="electronics", amount="1450.00", city="London", country="GB"
    )
    p.purchase(
        acct, 137, merchant="GiftCard Depot", category="gift_cards", amount="500.00", city="London", country="GB"
    )


def coordinated_ring(p: PlayContext) -> None:
    device = p.raw("ring-device")
    destination = "0990" + str(p.rng.randint(10**10, 10**11 - 1)) + "31"
    common = {
        "device_raw": device,
        "device_label": "Unrecognised laptop · Firefox",
        "platform": "linux",
        "ip_raw": p.raw("ring-ip"),
    }
    for i, acct in enumerate(p.accounts):
        base = i * 25
        loc = {"city": acct.home_city, "country": acct.home_country}
        p.security(acct, _E.ACCOUNT_RECOVERY_REQUESTED, base, outcome="success", **common, **loc)
        p.security(acct, _E.PASSWORD_RESET_REQUESTED, base + 4, outcome="success", **common, **loc)
        p.security(acct, _E.LOGIN_SUCCESS, base + 9, outcome="success", **common, **loc)
        p.security(
            acct,
            _E.AID_REDIRECT_REQUESTED,
            base + 14,
            outcome="requested",
            destination_raw=destination,
            **common,
            **loc,
        )
    end = p.at(len(p.accounts) * 25)
    for acct in p.accounts:  # relationship signals appear once the whole ring is visible
        accounts.reassess(p.db, acct, triggered_by="detection_run", at=end)


# ---------------------------------------------------------------- legitimate controls


def control_new_phone(p: PlayContext) -> None:
    acct = p.accounts[0]
    common = {
        "device_raw": p.raw("device"),
        "device_label": "New iPhone · Safari",
        "platform": "ios",
        "city": acct.home_city,
        "country": acct.home_country,
    }
    p.security(acct, _E.LOGIN_SUCCESS, 0, outcome="success", **common)
    p.security(acct, _E.MFA_PASSED, 1, outcome="success", **common)
    p.purchase(
        acct,
        95,
        merchant="FreshMart Grocery",
        category="groceries",
        amount="42.18",
        city=acct.home_city,
        country=acct.home_country,
    )


def control_travel(p: PlayContext) -> None:
    acct = p.accounts[0]
    for minutes, merchant, category, amount in (
        (0, "Metro Transit", "transport", "24.00"),
        (180, "Lakeview Diner", "dining", "17.40"),
        (1500, "City Museum Shop", "retail", "28.00"),
    ):
        p.purchase(acct, minutes, merchant=merchant, category=category, amount=amount, city="Chicago", country="US")


def control_study_abroad(p: PlayContext) -> None:
    acct = p.accounts[0]
    for minutes, merchant, category, amount in (
        (0, "Campus Café", "dining", "6.20"),
        (240, "City Grocer", "groceries", "38.90"),
        (1440, "University Bookshop", "bookstore", "54.00"),
    ):
        p.purchase(
            acct,
            minutes,
            merchant=merchant,
            category=category,
            amount=amount,
            city=acct.home_city,
            country=acct.home_country,
        )


def control_forgot_password(p: PlayContext) -> None:
    acct = p.accounts[0]
    device = next((d for d in _trusted_devices(p, acct)), None)
    common = {"device_raw": device, "city": acct.home_city, "country": acct.home_country} if device else {}
    p.security(acct, _E.LOGIN_FAILED, 0, outcome="failure", **common)
    p.security(acct, _E.LOGIN_FAILED, 1, outcome="failure", **common)
    p.security(acct, _E.PASSWORD_RESET_REQUESTED, 3, outcome="success", **common)
    p.security(acct, _E.MFA_PASSED, 4, outcome="success", **common)
    p.security(acct, _E.PASSWORD_CHANGED, 6, outcome="success", **common)


def _trusted_devices(p: PlayContext, acct: StudentFinancialAccount) -> list[str]:
    """Raw ids of the account's seeded trusted devices (the seeder derives them deterministically)."""
    from app.seed.accounts import trusted_device_raws

    return trusted_device_raws(acct)


@dataclass(frozen=True)
class ScenarioDef:
    key: str
    label: str
    kind: str  # "fraud" | "control"
    description: str
    expected: str
    expected_levels: tuple[str, ...]
    accounts_needed: int
    play: Callable[[PlayContext], None]
    live: bool = True
    span_minutes: int = 150  # how far back a live replay starts so every event is in the past


SCENARIOS: dict[str, ScenarioDef] = {
    s.key: s
    for s in (
        ScenarioDef(
            "lost_card",
            "Lost student ID card",
            "fraud",
            "Student reports a missing card: the report is recorded, the card is blocked through the sandbox "
            "provider, sensitive changes are held and a verification request opens. Two hours later someone "
            "tries the blocked card.",
            "High alert; card blocked; verification requested",
            ("high", "critical"),
            1,
            lost_card,
        ),
        ScenarioDef(
            "password_reset",
            "Suspicious password reset",
            "fraud",
            "An unknown session abroad fails three sign-ins, requests a password reset and fails the "
            "step-up challenge.",
            "Medium risk; additional authentication requested; no automatic block",
            ("medium", "high"),
            1,
            password_reset,
        ),
        ScenarioDef(
            "account_takeover",
            "New device and account takeover",
            "fraud",
            "Failed-sign-in burst, sign-in from an unfamiliar phone, password and recovery-contact change, "
            "then an attempt to redirect aid and move money out.",
            "Critical alert; sensitive actions held; verification workflow",
            ("high", "critical"),
            1,
            account_takeover,
        ),
        ScenarioDef(
            "suspicious_transaction",
            "Suspicious aid transaction",
            "fraud",
            "Card-present purchases abroad two hours after a campus purchase, far above the usual amount.",
            "High, explainable alert for investigator review; no automatic restriction",
            ("high", "critical"),
            1,
            suspicious_transaction,
        ),
        ScenarioDef(
            "coordinated_ring",
            "Coordinated financial aid fraud",
            "fraud",
            "One laptop runs account recovery on several students' accounts and redirects their aid to one "
            "external destination.",
            "Critical alerts on every account; linked cluster in Fraud Network",
            ("high", "critical"),
            5,
            coordinated_ring,
        ),
        ScenarioDef(
            "control_new_phone",
            "Legitimate: new phone",
            "control",
            "A student signs in on a new phone and passes additional authentication.",
            "Low risk; no alert",
            ("low",),
            1,
            control_new_phone,
        ),
        ScenarioDef(
            "control_travel",
            "Legitimate: weekend trip",
            "control",
            "Small purchases in another city over a weekend.",
            "Low risk; no alert",
            ("low",),
            1,
            control_travel,
            span_minutes=1520,
        ),
        ScenarioDef(
            "control_forgot_password",
            "Legitimate: forgotten password",
            "control",
            "Two failed sign-ins and a reset from the student's own device, confirmed by step-up.",
            "Low risk; no alert",
            ("low",),
            1,
            control_forgot_password,
        ),
        ScenarioDef(
            "control_study_abroad",
            "Legitimate: international student",
            "control",
            "A remote international student spends in their home city abroad.",
            "Low risk; no alert",
            ("low",),
            1,
            control_study_abroad,
            live=False,
            span_minutes=1460,
        ),
        ScenarioDef(
            "control_saver",
            "Legitimate: saving aid",
            "control",
            "An on-campus student has not spent from the account in over a month.",
            "Low risk; 'no local spending' shown as context only",
            ("low",),
            1,
            lambda p: None,
            live=False,
        ),
    )
}


def play(
    db: Session,
    key: str,
    accounts_: list[StudentFinancialAccount],
    *,
    start: datetime | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    scenario = SCENARIOS[key]
    start = start or utcnow() - timedelta(minutes=scenario.span_minutes + 5)
    ctx = PlayContext(db, accounts_, start, rng or random.Random(), key)
    for acct in accounts_:
        acct.scenario_key = key
    scenario.play(ctx)
    db.flush()
    return ctx.log
