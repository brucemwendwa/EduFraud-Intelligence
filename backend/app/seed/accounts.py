"""Synthetic student ID-linked accounts, cards, devices, transactions and security events.

Runs after the aid-record generator. Every student gets a provider-held financial aid account
(sandbox), a university ID card linked to it, one or two confirmed devices and a realistic,
deterministic history of everyday campus spending and sign-ins. Existing allocations
(disbursements) are linked to the account; those that were redirected elsewhere keep their
external destination, which is exactly what the risk engine looks for.

The five account scenarios and the legitimate controls are then replayed through the real
services (app.services.scenarios), and every account is scored once at the end.
"""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tokenization import TokenType, tokenize
from app.db.types import utcnow
from app.detection.account_engine import load_snapshot, score_transaction
from app.integrations.payment_provider import get_payment_provider
from app.models import (
    Device,
    Disbursement,
    EnrollmentRecord,
    FinancialAidApplication,
    Organization,
    PaymentDestinationToken,
    SecurityEvent,
    Student,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
)
from app.models.enums import (
    AccountStatus,
    CardStatus,
    DeviceTrust,
    DisbursementStatus,
    EnrollmentStatus,
    SecurityEventType,
    StudyMode,
    TransactionStatus,
)
from app.services import accounts as account_service
from app.services import scenarios

SEED = 20261031
_E = SecurityEventType

# (merchant, category, low, high, channel)
CAMPUS_MERCHANTS = (
    ("Union Dining Hall", "dining", 6, 18, "card_present"),
    ("Cardinal Coffee", "dining", 3, 9, "card_present"),
    ("FreshMart Grocery", "groceries", 12, 85, "card_present"),
    ("Campus Bookstore", "bookstore", 15, 140, "card_present"),
    ("Metro Transit", "transport", 2, 30, "card_present"),
    ("CampusPrint Services", "campus_services", 2, 20, "card_present"),
    ("Laundry Plus", "campus_services", 3, 12, "card_present"),
    ("Pharmacy Express", "health", 8, 45, "card_present"),
    ("QuickFuel", "fuel", 20, 55, "card_present"),
    ("Campus ATM", "cash_withdrawal", 20, 100, "atm"),
    ("Textbook Exchange Online", "bookstore", 25, 160, "online"),
    ("StreamBox Subscription", "subscriptions", 8, 16, "online"),
)
_WEIGHTS = (16, 14, 14, 6, 8, 4, 5, 4, 4, 4, 4, 3)
REMOTE_CITIES = (("Columbus", "US"), ("Pittsburgh", "US"), ("Chicago", "US"), ("Louisville", "US"), ("Nashville", "US"))
INTERNATIONAL = (("Toronto", "CA"), ("Bengaluru", "IN"), ("Monterrey", "MX"), ("Berlin", "DE"), ("Seoul", "KR"))
TRIP_CITIES = {"US": ("Cleveland", "Indianapolis", "Detroit", "Atlanta")}
PHONES = ("iPhone · Safari", "Android phone · Chrome", "Pixel phone · Chrome")
LAPTOPS = ("MacBook · Safari", "Windows laptop · Edge", "Chromebook · Chrome")


def trusted_device_raws(account: StudentFinancialAccount) -> list[str]:
    """Deterministic raw ids of the devices the seeder registers for an account (never stored in clear)."""
    return [f"seed-device-{account.reference}-{i}" for i in range(2)]


@dataclass
class AccountSeedSummary:
    accounts: int = 0
    cards: int = 0
    transactions: int = 0
    security_events: int = 0
    scenario_refs: dict[str, list[str]] = field(default_factory=dict)


class AccountSeeder:
    def __init__(self, db: Session, orgs: dict[str, Organization], seed: int = SEED, now: datetime | None = None):
        self.db = db
        self.orgs = orgs
        self.rng = random.Random(seed)
        self.now = now or utcnow()
        self.summary = AccountSeedSummary()
        self._acct_seq = 104_200
        self._card_seq = 300_000
        self._txn_seq = 0
        self._sev_seq = 0
        self._txn_count: dict[uuid.UUID, int] = defaultdict(int)
        self._spent: dict[uuid.UUID, Decimal] = defaultdict(Decimal)

    # ------------------------------------------------------------------ helpers
    def _when(self, days_ago: float, hour: int | None = None) -> datetime:
        moment = self.now - timedelta(days=days_ago)
        if hour is not None:
            moment = moment.replace(hour=hour, minute=self.rng.randint(0, 59), second=self.rng.randint(0, 59))
        return min(moment, self.now - timedelta(minutes=5))

    def _event(
        self,
        acct: StudentFinancialAccount,
        event_type: str,
        at: datetime,
        device: Device | None,
        outcome: str = "success",
        city: str | None = None,
        country: str | None = None,
    ) -> None:
        self._sev_seq += 1
        self.db.add(
            SecurityEvent(
                organization_id=acct.organization_id,
                student_id=acct.student_id,
                account_id=acct.id,
                device_id=device.id if device else None,
                reference=f"SEV-{self._sev_seq:06d}",
                provider_event_id=f"seed-sev-{self._sev_seq}",
                event_type=event_type,
                source="identity_provider_sandbox",
                outcome=outcome,
                occurred_at=at,
                session_token=tokenize(TokenType.SESSION, f"seed-session-{self._sev_seq}"),
                ip_token=tokenize(TokenType.IP, f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.7"),
                location_city=city or acct.home_city,
                location_country=country or acct.home_country,
                details={},
                created_at=at,
            )
        )
        self.summary.security_events += 1

    def _txn(
        self,
        acct: StudentFinancialAccount,
        card: StudentIDCard,
        at: datetime,
        merchant: str,
        category: str,
        amount: float,
        channel: str,
        city: str | None = None,
        country: str | None = None,
    ) -> None:
        self._txn_seq += 1
        online = channel == "online"
        self.db.add(
            Transaction(
                organization_id=acct.organization_id,
                account_id=acct.id,
                card_id=None if online else card.id,
                student_id=acct.student_id,
                reference=f"TXN-{self._txn_seq:07d}",
                provider_event_id=f"seed-txn-{self._txn_seq}",
                transaction_type="atm_withdrawal" if channel == "atm" else "purchase",
                channel=channel,
                merchant_name=merchant,
                merchant_category=category,
                merchant_token=tokenize(TokenType.MERCHANT, merchant),
                amount=Decimal(f"{amount:.2f}"),
                occurred_at=at,
                location_city=None if online else (city or acct.home_city),
                location_country=None if online else (country or acct.home_country),
                status=TransactionStatus.APPROVED,
                risk_indicators=[],
            )
        )
        acct.last_transaction_at = max(filter(None, (acct.last_transaction_at, at)))
        self._txn_count[acct.id] += 1
        self._spent[acct.id] += Decimal(f"{amount:.2f}")
        self.summary.transactions += 1

    # ------------------------------------------------------------------ accounts
    def account_for(
        self,
        stu: Student,
        org: Organization,
        *,
        study_mode: str | None = None,
        home: tuple[str, str] | None = None,
        closed: bool = False,
    ) -> tuple[StudentFinancialAccount, StudentIDCard]:
        self._acct_seq += self.rng.randint(1, 6)
        mode = (
            study_mode
            or self.rng.choices([StudyMode.ON_CAMPUS, StudyMode.REMOTE_DOMESTIC, StudyMode.INTERNATIONAL], [82, 11, 7])[
                0
            ]
        )
        city, country = home or (
            (org.city, "US")
            if mode == StudyMode.ON_CAMPUS
            else self.rng.choice(REMOTE_CITIES if mode == StudyMode.REMOTE_DOMESTIC else INTERNATIONAL)
        )
        opened = self._when(self.rng.uniform(75, 140), hour=10)
        reference = f"SFA-{self._acct_seq:06d}"
        acct = StudentFinancialAccount(
            organization_id=org.id,
            student_id=stu.id,
            reference=reference,
            provider_key=get_payment_provider().key,
            provider_mode=get_payment_provider().mode,
            provider_account_token=tokenize(TokenType.PROVIDER_ACCOUNT, f"SBX-ACCT-{reference}"),
            status=AccountStatus.CLOSED if closed else AccountStatus.ACTIVE,
            status_reason="Student withdrew; account closed by the provider" if closed else None,
            study_mode=mode,
            home_city=city,
            home_country=country,
            opened_at=opened,
            currency="USD",
        )
        self.db.add(acct)
        self._card_seq += self.rng.randint(1, 4)
        serial = f"SBX-CARD-{self._card_seq:08d}"
        card = StudentIDCard(
            organization_id=org.id,
            student_id=stu.id,
            account_id=acct.id,
            reference=f"CRD-{self._card_seq:06d}",
            card_token=tokenize(TokenType.CARD, serial),
            display_suffix=serial[-4:],
            status=CardStatus.BLOCKED if closed else CardStatus.ACTIVE,
            issued_at=opened,
            activated_at=opened + timedelta(days=1),
            expires_on=date(opened.year + 4, 8, 31),
        )
        self.db.add(card)
        self.summary.accounts += 1
        self.summary.cards += 1
        return acct, card

    def devices_for(self, acct: StudentFinancialAccount) -> list[Device]:
        labels = [self.rng.choice(PHONES)] + ([self.rng.choice(LAPTOPS)] if self.rng.random() < 0.7 else [])
        out = []
        for raw, label in zip(trusted_device_raws(acct), labels, strict=False):
            device = Device(
                organization_id=acct.organization_id,
                student_id=acct.student_id,
                device_token=tokenize(TokenType.DEVICE, raw),
                label=label,
                platform=label.split(" ")[0].lower(),
                trust_status=DeviceTrust.TRUSTED,
                trust_reason="Registered at account opening",
                first_seen_at=acct.opened_at,
                last_seen_at=acct.opened_at,
            )
            self.db.add(device)
            out.append(device)
        return out

    def history(
        self, acct: StudentFinancialAccount, card: StudentIDCard, devices: list[Device], *, saver: bool = False
    ) -> None:
        """Everyday spending and sign-ins over the last ~60 days."""
        span = min(60.0, (self.now - acct.opened_at).days - 1)
        if not saver:
            for _ in range(self.rng.randint(6, 16)):
                i = self.rng.choices(range(len(CAMPUS_MERCHANTS)), _WEIGHTS)[0]
                merchant, category, low, high, channel = CAMPUS_MERCHANTS[i]
                self._txn(
                    acct,
                    card,
                    self._when(self.rng.uniform(0.3, span), hour=self.rng.randint(8, 21)),
                    merchant,
                    category,
                    self.rng.uniform(low, high),
                    channel,
                )
            if acct.home_country == "US" and self.rng.random() < 0.08:  # a weekend trip
                trip = self.rng.choice(TRIP_CITIES["US"])
                day = self.rng.uniform(5, span - 2)
                for k in range(2):
                    self._txn(
                        acct,
                        card,
                        self._when(day - k * 0.4, hour=13),
                        "Highway Diner",
                        "dining",
                        self.rng.uniform(9, 24),
                        "card_present",
                        city=trip,
                        country="US",
                    )
        for _ in range(self.rng.randint(2, 6)):
            device = self.rng.choice(devices)
            at = self._when(self.rng.uniform(0.5, span), hour=self.rng.randint(7, 23))
            self._event(acct, _E.LOGIN_SUCCESS, at, device)
            device.last_seen_at = max(device.last_seen_at, at)
        roll = self.rng.random()
        if roll < 0.08:  # forgot password: a failed attempt, then success on a known device
            at = self._when(self.rng.uniform(1, 20), hour=9)
            self._event(acct, _E.LOGIN_FAILED, at, devices[0], outcome="failure")
            self._event(acct, _E.LOGIN_SUCCESS, at + timedelta(minutes=2), devices[0])
        elif roll < 0.14:  # new phone, confirmed by additional authentication
            raw = f"seed-device-{acct.reference}-new"
            at = self._when(self.rng.uniform(1, 25), hour=18)
            phone = Device(
                organization_id=acct.organization_id,
                student_id=acct.student_id,
                device_token=tokenize(TokenType.DEVICE, raw),
                label=self.rng.choice(PHONES),
                platform="phone",
                trust_status=DeviceTrust.TRUSTED,
                trust_reason="Confirmed by additional authentication",
                first_seen_at=at,
                last_seen_at=at,
            )
            self.db.add(phone)
            self.db.flush()
            self._event(acct, _E.NEW_DEVICE_LOGIN, at, phone)
            self._event(acct, _E.MFA_PASSED, at + timedelta(minutes=1), phone)

    def link_allocations(self, acct: StudentFinancialAccount) -> None:
        """Allocations belong to the account; unchanged, single-student destinations become the account itself."""
        own = PaymentDestinationToken(
            token_value=acct.provider_account_token,
            destination_type="id_card_account",
            display_suffix=acct.reference[-2:],
            first_seen_at=acct.opened_at,
        )
        self.db.add(own)
        self.db.flush()
        credited = Decimal("0")
        for d in self.db.scalars(select(Disbursement).where(Disbursement.student_id == acct.student_id)):
            d.account_id = acct.id
            shared = self.db.scalar(
                select(Disbursement.id).where(
                    Disbursement.destination_id == d.destination_id, Disbursement.student_id != acct.student_id
                )
            )
            if d.destination_changed_at is None and shared is None:
                d.destination_id = own.id
                if d.status == DisbursementStatus.RELEASED:
                    credited += d.amount
        acct.available_balance = get_payment_provider().balance(credited, self._spent[acct.id])
        acct.balance_as_of = self.now - timedelta(minutes=20)

    # ------------------------------------------------------------------ run
    def baseline(self) -> dict[uuid.UUID, tuple[StudentFinancialAccount, StudentIDCard]]:
        out = {}
        withdrawn = set(
            self.db.scalars(
                select(EnrollmentRecord.student_id).where(EnrollmentRecord.status == EnrollmentStatus.WITHDRAWN)
            )
        )
        students = self.db.scalars(select(Student).order_by(Student.student_ref)).all()
        orgs = {o.id: o for o in self.orgs.values()}
        for stu in students:
            closed = stu.id in withdrawn
            acct, card = self.account_for(stu, orgs[stu.organization_id], closed=closed)
            self.db.flush()
            devices = self.devices_for(acct)
            self.db.flush()
            if not closed:
                self.history(acct, card, devices, saver=self.rng.random() < 0.04)
            self.link_allocations(acct)
            out[stu.id] = (acct, card)
        self.db.flush()
        return out

    def pick(
        self,
        by_student: dict,
        org_slug: str,
        n: int,
        *,
        exclude: set,
        study_mode: str = StudyMode.ON_CAMPUS,
        min_txns: int = 6,
    ) -> list[StudentFinancialAccount]:
        org = self.orgs[org_slug]
        scenario_students = set(
            self.db.scalars(
                select(FinancialAidApplication.student_id).where(FinancialAidApplication.scenario_key.is_not(None))
            )
        )
        chosen = []
        for acct, _card in by_student.values():
            if (
                acct.organization_id != org.id
                or acct.id in exclude
                or acct.student_id in scenario_students
                or acct.status != AccountStatus.ACTIVE
                or acct.study_mode != study_mode
            ):
                continue
            if study_mode == StudyMode.ON_CAMPUS and self._txn_count[acct.id] < min_txns:
                continue
            chosen.append(acct)
            exclude.add(acct.id)
            if len(chosen) == n:
                return chosen
        raise RuntimeError(f"Not enough eligible synthetic accounts at {org_slug} for a scenario")

    def run(self) -> AccountSeedSummary:
        by_student = self.baseline()
        # Score the bulk history once (as of now) before replaying scenarios on top of it.
        for acct, _ in by_student.values():
            snap = load_snapshot(self.db, acct, now=self.now)
            for txn in snap.transactions:
                score_transaction(snap, txn)
        self.db.flush()

        used: set = set()
        plan = (
            ("control_saver", "northbridge", 1, StudyMode.ON_CAMPUS, 6.0),
            ("control_new_phone", "northbridge", 1, StudyMode.ON_CAMPUS, 6.5),
            ("control_travel", "northbridge", 1, StudyMode.ON_CAMPUS, 8.0),
            ("control_forgot_password", "northbridge", 1, StudyMode.ON_CAMPUS, 3.2),
            ("control_study_abroad", "northbridge", 1, StudyMode.INTERNATIONAL, 4.0),
            ("suspicious_transaction", "northbridge", 1, StudyMode.ON_CAMPUS, 2.3),
            ("password_reset", "northbridge", 1, StudyMode.ON_CAMPUS, 1.4),
            ("lost_card", "northbridge", 1, StudyMode.ON_CAMPUS, 4.6),
            ("account_takeover", "northbridge", 1, StudyMode.ON_CAMPUS, 0.9),
            ("coordinated_ring", "northbridge", 5, StudyMode.ON_CAMPUS, 2.8),
            ("lost_card", "lakeshore", 1, StudyMode.ON_CAMPUS, 3.4),
            ("account_takeover", "lakeshore", 1, StudyMode.ON_CAMPUS, 5.1),
        )
        for key, slug, n, mode, days_ago in plan:
            chosen = self.pick(by_student, slug, n, exclude=used, study_mode=mode)
            if key == "coordinated_ring":  # one member at another institution: shown only as an anonymous link
                chosen += self.pick(by_student, "lakeshore", 1, exclude=used)
            if key == "control_saver":
                self._make_saver(chosen[0])
            scenarios.play(self.db, key, chosen, start=self._when(days_ago, hour=14), rng=self.rng)
            self.summary.scenario_refs.setdefault(key, []).extend(a.reference for a in chosen)

        for acct, _ in by_student.values():
            account_service.reassess(self.db, acct, triggered_by="detection_run", at=self.now)
        self.db.flush()
        return self.summary

    def _make_saver(self, acct: StudentFinancialAccount) -> None:
        """A student who saves their aid: no card spending at all (only sign-ins)."""
        for txn in self.db.scalars(select(Transaction).where(Transaction.account_id == acct.id)):
            self.db.delete(txn)
        self.db.flush()
        acct.last_transaction_at = None
        acct.opened_at = min(acct.opened_at, self.now - timedelta(days=70))


def seed_accounts(db: Session, orgs: dict[str, Organization]) -> AccountSeedSummary:
    return AccountSeeder(db, orgs).run()
