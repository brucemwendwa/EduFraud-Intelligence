"""Deterministic synthetic data generator for demonstrations and tests.

Every record is fictional and flagged `is_synthetic`. Raw identifiers (SSN, date of
birth, phone, bank account, device ids) exist only as local variables while being
tokenized; they are never persisted. SSNs use area number 000, which the Social
Security Administration never issues.

Besides a realistic baseline, the generator plants documented scenarios
(see docs/demo-script.md) tagged with `scenario_key`:

  identity_impersonation, duplicate_identity, shared_destination,
  unusual_disbursement, coordinated_network                (should be flagged)
  control_siblings, control_dorm, control_transfer,
  control_bank_change, control_high_need                  (legitimate: should NOT be high risk)
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.tokenization import TokenType, tokenize
from app.db.types import utcnow
from app.models import (
    Disbursement,
    EnrollmentRecord,
    FinancialAidApplication,
    IdentityVerification,
    Organization,
    PaymentDestinationToken,
    Student,
    StudentIdentityToken,
)
from app.models.enums import (
    ApplicationStatus,
    DisbursementStatus,
    EnrollmentStatus,
    FundType,
    Modality,
    ReviewStatus,
    VerificationMethod,
    VerificationStatus,
    VerificationTrigger,
)
from app.seed.vocab import FIRST_NAMES, LAST_NAMES, PROGRAMS, STATES, STREET_SUFFIXES, STREETS

SEED = 20261030
BASELINE_COUNTS = {"northbridge": 220, "lakeshore": 140, "pinecrest": 90}

FLAGGED_SCENARIOS = (
    "identity_impersonation",
    "duplicate_identity",
    "shared_destination",
    "unusual_disbursement",
    "coordinated_network",
)
CONTROL_SCENARIOS = (
    "control_siblings",
    "control_dorm",
    "control_transfer",
    "control_bank_change",
    "control_high_need",
)


@dataclass
class Identity:
    """Raw synthetic attributes of one person. Lives only in memory during generation."""

    first: str
    last: str
    dob: date
    ssn: str
    email: str
    phone: str
    address: str


@dataclass
class GenerationSummary:
    students: int = 0
    applications: int = 0
    disbursements: int = 0
    verifications: int = 0
    scenario_refs: dict[str, list[str]] = field(default_factory=dict)


class SyntheticGenerator:
    def __init__(self, db: Session, orgs: dict[str, Organization], seed: int = SEED, now: datetime | None = None):
        self.db = db
        self.orgs = orgs
        self.rng = random.Random(seed)
        self.now = now or utcnow()
        self.summary = GenerationSummary()
        self._ssns: set[str] = set()
        self._app_seq = 104_000
        self._dsb_seq = 560_000
        self._idv_seq = 30_000
        self._stu_seq = 0
        # Current term starts ~10 weeks before "now" so the data always looks recent.
        self.term_start: date = (self.now - timedelta(days=67)).date()
        self.term = f"{'Fall' if self.term_start.month >= 7 else 'Spring'} {self.term_start.year}"
        start_year = self.term_start.year if self.term_start.month >= 7 else self.term_start.year - 1
        self.award_year = f"{start_year}-{(start_year + 1) % 100:02d}"

    # ------------------------------------------------------------------ primitives
    def _at(self, days_ago: float, hour: int | None = None) -> datetime:
        moment = self.now - timedelta(days=days_ago)
        if hour is not None:
            moment = moment.replace(hour=hour, minute=self.rng.randint(0, 59), second=self.rng.randint(0, 59))
        return moment

    def _term_day(self, offset_days: int, hour: int = 10) -> datetime:
        d = self.term_start + timedelta(days=offset_days)
        return datetime(d.year, d.month, d.day, hour, self.rng.randint(0, 59), tzinfo=self.now.tzinfo)

    def _fake_ssn(self) -> str:
        while True:
            ssn = f"000-{self.rng.randint(10, 99)}-{self.rng.randint(1000, 9999)}"
            if ssn not in self._ssns:
                self._ssns.add(ssn)
                return ssn

    def _phone(self) -> str:
        # 555-0100..0199 is reserved for fictional use.
        return f"({self.rng.randint(200, 989)}) 555-01{self.rng.randint(0, 99):02d}"

    def _address(self, org: Organization) -> str:
        return (
            f"{self.rng.randint(100, 9899)} {self.rng.choice(STREETS)} {self.rng.choice(STREET_SUFFIXES)}, "
            f"{org.city}, {org.state}"
        )

    def identity(self, org: Organization, *, age: int | None = None, **overrides: object) -> Identity:
        first, last = self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)
        age = age or int(self.rng.choices([18, 19, 20, 21, 22, 24, 27, 31, 38], [16, 16, 14, 12, 10, 10, 9, 8, 5])[0])
        dob = date(self.now.year - age, self.rng.randint(1, 12), self.rng.randint(1, 28))
        ident = Identity(
            first=first,
            last=last,
            dob=dob,
            ssn=self._fake_ssn(),
            email=f"{first}.{last}{self.rng.randint(1, 999)}@mail.example".lower(),
            phone=self._phone(),
            address=self._address(org),
        )
        for key, value in overrides.items():
            setattr(ident, key, value)
        return ident

    def student(
        self, org: Organization, ident: Identity, *, consent: bool | None = None, consent_days_ago: int = 200
    ) -> Student:
        self._stu_seq += 1
        consent = self.rng.random() < 0.72 if consent is None else consent
        stu = Student(
            organization_id=org.id,
            student_ref=f"STU-{self._stu_seq:05d}",
            first_name=ident.first,
            last_name=ident.last,
            birth_year=ident.dob.year,
            state_of_residence=org.state if self.rng.random() < 0.8 else self.rng.choice(STATES),
            biometric_consent=consent,
            biometric_consent_at=self._at(consent_days_ago) if consent else None,
            biometric_reference_id=f"sim-tpl-{uuid.uuid4().hex[:16]}" if consent else None,
        )
        tokens = {
            TokenType.SSN: ident.ssn,
            TokenType.DOB: ident.dob.isoformat(),
            TokenType.NAME: f"{ident.first} {ident.last}",
            TokenType.EMAIL: ident.email,
            TokenType.PHONE: ident.phone,
            TokenType.ADDRESS: ident.address,
        }
        stu.identity_tokens = [
            StudentIdentityToken(organization_id=org.id, token_type=t.value, token_value=tokenize(t, v))
            for t, v in tokens.items()
        ]
        self.db.add(stu)
        self.summary.students += 1
        return stu

    def application(
        self,
        org: Organization,
        stu: Student,
        *,
        submitted_at: datetime,
        device: str | None = None,
        ip: str | None = None,
        scenario: str | None = None,
        status: ApplicationStatus | None = None,
        requested: int | None = None,
        sai: int | None = None,
        intensity: str | None = None,
        program: str | None = None,
        dependency: str | None = None,
        channel: str | None = None,
    ) -> FinancialAidApplication:
        self._app_seq += self.rng.randint(1, 9)
        age = self.now.year - stu.birth_year
        status = (
            status
            or self.rng.choices(
                [
                    ApplicationStatus.APPROVED,
                    ApplicationStatus.IN_REVIEW,
                    ApplicationStatus.RECEIVED,
                    ApplicationStatus.ON_HOLD,
                ],
                [62, 18, 17, 3],
            )[0]
        )
        app = FinancialAidApplication(
            organization_id=org.id,
            student_id=stu.id,
            reference=f"FA-{self.award_year[:4]}-{self._app_seq:06d}",
            award_year=self.award_year,
            submitted_at=submitted_at,
            status=status,
            dependency_status=dependency or ("dependent" if age < 24 and self.rng.random() < 0.8 else "independent"),
            enrollment_intensity=intensity
            or self.rng.choices(["full_time", "three_quarter_time", "half_time"], [70, 15, 15])[0],
            program=program or self.rng.choice(PROGRAMS[org.institution_type]),
            requested_amount=Decimal(requested or self.rng.randrange(2500, 12500, 50)),
            student_aid_index=sai if sai is not None else int(self.rng.triangular(-1500, 32000, 4000)),
            submission_channel=channel or self.rng.choices(["online", "mobile", "paper"], [84, 13, 3])[0],
            device_token=tokenize(TokenType.DEVICE, device or uuid.UUID(int=self.rng.getrandbits(128)).hex),
            ip_token=tokenize(
                TokenType.IP,
                ip or f"10.{self.rng.randint(0, 255)}.{self.rng.randint(0, 255)}.{self.rng.randint(1, 254)}",
            ),
            verification_status=VerificationStatus.NOT_REQUIRED,
            review_status=ReviewStatus.CLEARED if status == ApplicationStatus.APPROVED else ReviewStatus.UNREVIEWED,
            scenario_key=scenario,
        )
        app.student = stu
        self.db.add(app)
        self.db.flush()  # dependants (enrollment, disbursements) reference it without an ORM relationship
        self.summary.applications += 1
        if scenario:
            self.summary.scenario_refs.setdefault(scenario, []).append(app.reference)
        return app

    def enrollment(
        self,
        org: Organization,
        stu: Student,
        app: FinancialAidApplication | None,
        *,
        modality: Modality | None = None,
        status: EnrollmentStatus = EnrollmentStatus.ENROLLED,
        credit_hours: int | None = None,
        attended: bool = True,
        term: str | None = None,
        term_start: date | None = None,
    ) -> EnrollmentRecord:
        online_share = 0.45 if org.institution_type == "community_college" else 0.18
        modality = modality or (
            Modality.ONLINE
            if self.rng.random() < online_share
            else self.rng.choices([Modality.IN_PERSON, Modality.HYBRID], [75, 25])[0]
        )
        record = EnrollmentRecord(
            organization_id=org.id,
            student_id=stu.id,
            application_id=app.id if app else None,
            term=term or self.term,
            term_start=term_start or self.term_start,
            program=app.program if app else self.rng.choice(PROGRAMS[org.institution_type]),
            credit_hours=credit_hours or self.rng.choice([6, 9, 12, 12, 13, 15, 15, 16, 18]),
            modality=modality,
            status=status,
            last_attendance_at=self._at(self.rng.uniform(0.5, 6)) if attended else None,
        )
        self.db.add(record)
        return record

    def destination(self, *, kind: str = "bank_account", raw: str | None = None) -> PaymentDestinationToken:
        # Synthetic routing+account digits (tokenization keeps digits only for bank accounts).
        raw = raw or f"0{self.rng.randint(10**8, 10**9 - 1)}{self.rng.randint(10**9, 10**12 - 1)}"
        dest = PaymentDestinationToken(
            token_value=tokenize(TokenType.BANK_ACCOUNT, raw),
            destination_type=kind,
            display_suffix=f"{self.rng.randint(0, 99):02d}",
            first_seen_at=self._at(self.rng.uniform(60, 400)),
        )
        self.db.add(dest)
        return dest

    def disbursement(
        self,
        org: Organization,
        stu: Student,
        app: FinancialAidApplication,
        dest: PaymentDestinationToken,
        *,
        fund: FundType,
        amount: float,
        when: datetime,
        destination_changed_at: datetime | None = None,
    ) -> Disbursement:
        self._dsb_seq += self.rng.randint(1, 7)
        d = Disbursement(
            organization_id=org.id,
            student_id=stu.id,
            application_id=app.id,
            reference=f"DSB-{self._dsb_seq:06d}",
            fund_type=fund,
            amount=Decimal(f"{amount:.2f}"),
            disbursed_at=when,
            status=DisbursementStatus.SCHEDULED if when > self.now else DisbursementStatus.RELEASED,
            destination_changed_at=destination_changed_at,
            risk_flags=[],
        )
        d.destination = dest
        d.student = stu
        self.db.add(d)
        self.summary.disbursements += 1
        return d

    def passed_verification(
        self,
        org: Organization,
        stu: Student,
        app: FinancialAidApplication,
        *,
        when: datetime,
        trigger: VerificationTrigger,
    ) -> IdentityVerification:
        """A historical, successful verification (biometric if consented, otherwise in person)."""
        self._idv_seq += self.rng.randint(1, 5)
        biometric = stu.biometric_consent
        v = IdentityVerification(
            organization_id=org.id,
            student_id=stu.id,
            application_id=app.id,
            reference=f"IDV-{self._idv_seq:06d}",
            trigger=trigger,
            method=VerificationMethod.DOCUMENT_BIOMETRIC if biometric else VerificationMethod.IN_PERSON_ID_CHECK,
            provider="edushield-simulated-idv" if biometric else "manual",
            provider_mode="simulation" if biometric else "manual",
            status="passed",
            document_result="authentic",
            document_type="drivers_license",
            face_match_score=round(self.rng.uniform(0.91, 0.99), 3) if biometric else None,
            liveness_score=round(self.rng.uniform(0.9, 0.99), 3) if biometric else None,
            liveness_result="live" if biometric else "not_performed",
            pad_result="none_detected" if biometric else "not_performed",
            quality_flags=[],
            risk_indicators=[],
            recommended_action="No action needed. Identity confirmed.",
            sample_key="enrolled_student" if biometric else None,
            notes=None if biometric else "Government photo ID inspected in person at the financial aid office.",
            completed_at=when,
            created_at=when,
        )
        self.db.add(v)
        app.verification_status = VerificationStatus.PASSED
        self.summary.verifications += 1
        return v

    def _amount(self, fund: FundType) -> float:
        low, high = {
            FundType.PELL_GRANT: (1200, 3697),
            FundType.DIRECT_SUBSIDIZED: (1750, 2750),
            FundType.DIRECT_UNSUBSIDIZED: (1000, 3000),
            FundType.INSTITUTIONAL_GRANT: (500, 2500),
            FundType.CREDIT_BALANCE_REFUND: (300, 3200),
        }[fund]
        return round(self.rng.uniform(low, high), -1)

    def standard_disbursements(
        self,
        org: Organization,
        stu: Student,
        app: FinancialAidApplication,
        dest: PaymentDestinationToken,
        *,
        refund: bool | None = None,
    ) -> list[Disbursement]:
        """Typical term disbursements: grant, maybe loans, maybe a credit-balance refund to the student."""
        out = []
        if app.student_aid_index < 7000 or self.rng.random() < 0.25:
            out.append(
                self.disbursement(
                    org,
                    stu,
                    app,
                    dest,
                    fund=FundType.PELL_GRANT,
                    amount=self._amount(FundType.PELL_GRANT),
                    when=self._term_day(-9),
                )
            )
        if self.rng.random() < 0.55:
            fund = self.rng.choice([FundType.DIRECT_SUBSIDIZED, FundType.DIRECT_UNSUBSIDIZED])
            out.append(
                self.disbursement(
                    org,
                    stu,
                    app,
                    dest,
                    fund=fund,
                    amount=self._amount(fund),
                    when=self._term_day(self.rng.choice([-9, 30])),
                )
            )
        if self.rng.random() < 0.2:
            out.append(
                self.disbursement(
                    org,
                    stu,
                    app,
                    dest,
                    fund=FundType.INSTITUTIONAL_GRANT,
                    amount=self._amount(FundType.INSTITUTIONAL_GRANT),
                    when=self._term_day(-9),
                )
            )
        if refund if refund is not None else (out and self.rng.random() < 0.45):
            out.append(
                self.disbursement(
                    org,
                    stu,
                    app,
                    dest,
                    fund=FundType.CREDIT_BALANCE_REFUND,
                    amount=self._amount(FundType.CREDIT_BALANCE_REFUND),
                    when=self._term_day(self.rng.randint(12, 40), hour=self.rng.randint(8, 17)),
                )
            )
        return out

    # ------------------------------------------------------------------ baseline
    def baseline_student(self, org: Organization, *, kiosk_device: str | None = None) -> FinancialAidApplication:
        ident = self.identity(org)
        stu = self.student(org, ident)
        self.db.flush()
        submitted = self._at(self.rng.triangular(3, 190, 70), hour=int(self.rng.triangular(7, 23, 14)))
        app = self.application(org, stu, submitted_at=submitted, device=kiosk_device)
        attended = self.rng.random() > 0.02
        status = EnrollmentStatus.ENROLLED if attended else EnrollmentStatus.WITHDRAWN
        self.enrollment(org, stu, app, status=status, attended=attended)
        self.db.flush()
        if app.status == ApplicationStatus.APPROVED:
            self.standard_disbursements(org, stu, app, self.destination())
            if self.rng.random() < 0.18:
                self.passed_verification(
                    org, stu, app, when=self._term_day(-14), trigger=VerificationTrigger.PRE_DISBURSEMENT
                )
        return app

    def baseline(self) -> None:
        for slug, count in BASELINE_COUNTS.items():
            org = self.orgs[slug]
            # A shared campus-library kiosk: many legitimate applications from one device, spread over months.
            kiosk = f"kiosk-{slug}-library"
            for i in range(count):
                self.baseline_student(org, kiosk_device=kiosk if i % 23 == 0 else None)
        self.db.flush()

    # ------------------------------------------------------------------ fraud scenarios
    def scenario_identity_impersonation(self, ring_destination: PaymentDestinationToken) -> None:
        """A legitimate student whose account is targeted: someone requests a refund-destination change.

        The step-up biometric verification that fails is produced by the verification service
        during seeding (see seed pipeline), exactly as it would be at runtime.
        """
        org = self.orgs["northbridge"]
        ident = self.identity(org, age=20, first="Maya", last="Robinson")
        stu = self.student(org, ident, consent=True, consent_days_ago=320)
        self.db.flush()
        app = self.application(
            org,
            stu,
            submitted_at=self._at(140, hour=19),
            scenario="identity_impersonation",
            status=ApplicationStatus.APPROVED,
            program="B.S. Nursing",
            sai=1200,
            intensity="full_time",
        )
        self.enrollment(org, stu, app, modality=Modality.IN_PERSON, credit_hours=15)
        self.db.flush()
        own = self.destination()
        self.disbursement(org, stu, app, own, fund=FundType.PELL_GRANT, amount=3480, when=self._term_day(-9))
        self.disbursement(org, stu, app, own, fund=FundType.DIRECT_SUBSIDIZED, amount=1750, when=self._term_day(-9))
        self.passed_verification(org, stu, app, when=self._term_day(-20), trigger=VerificationTrigger.PRE_DISBURSEMENT)
        # Pending refund now pointed at an unfamiliar destination (changed yesterday) — linked to the ring below.
        self.disbursement(
            org,
            stu,
            app,
            ring_destination,
            fund=FundType.CREDIT_BALANCE_REFUND,
            amount=2450,
            when=self.now + timedelta(days=2),
            destination_changed_at=self._at(1, hour=2),
        )

    def scenario_duplicate_identity(self) -> None:
        """One SSN behind four applications with conflicting names/DOBs, same device, one overnight burst."""
        ssn = self._fake_ssn()
        device = "dup-ring-laptop-7731"
        burst = self._at(9, hour=2)
        plan = [("northbridge", 0), ("northbridge", 11), ("northbridge", 24), ("lakeshore", 38)]
        for slug, minutes in plan:
            org = self.orgs[slug]
            ident = self.identity(org, age=self.rng.choice([22, 26, 29]), ssn=ssn)
            stu = self.student(org, ident, consent=False)
            self.db.flush()
            app = self.application(
                org,
                stu,
                submitted_at=burst + timedelta(minutes=minutes),
                device=device,
                ip="203.0.113.77",
                scenario="duplicate_identity",
                status=ApplicationStatus.RECEIVED,
                requested=12500,
                sai=-1500,
                dependency="independent",
                channel="online",
            )
            self.enrollment(
                org,
                stu,
                app,
                modality=Modality.ONLINE,
                credit_hours=6,
                attended=False,
                status=EnrollmentStatus.ENROLLED,
            )

    def scenario_shared_destination(self) -> PaymentDestinationToken:
        """Six otherwise-unrelated students whose refunds all go to one prepaid card."""
        card = self.destination(kind="prepaid_card", raw="0990000000000100001")
        plan = ["northbridge"] * 4 + ["pinecrest"] * 2
        for i, slug in enumerate(plan):
            org = self.orgs[slug]
            stu = self.student(org, self.identity(org))
            self.db.flush()
            app = self.application(
                org,
                stu,
                submitted_at=self._at(self.rng.uniform(40, 120), hour=15),
                scenario="shared_destination",
                status=ApplicationStatus.APPROVED,
                sai=500,
            )
            self.enrollment(org, stu, app)
            self.db.flush()
            self.disbursement(
                org,
                stu,
                app,
                self.destination(),
                fund=FundType.PELL_GRANT,
                amount=self._amount(FundType.PELL_GRANT),
                when=self._term_day(-9),
            )
            self.disbursement(
                org,
                stu,
                app,
                card,
                fund=FundType.CREDIT_BALANCE_REFUND,
                amount=round(self.rng.uniform(1400, 2900), -1),
                when=self._term_day(18 + i * 3, hour=11),
                destination_changed_at=self._term_day(14 + i * 3, hour=23),
            )
        return card

    def scenario_unusual_disbursement(self) -> None:
        """An outsized refund plus a burst of three disbursements within five days."""
        org = self.orgs["northbridge"]
        stu = self.student(org, self.identity(org, age=24))
        self.db.flush()
        app = self.application(
            org,
            stu,
            submitted_at=self._at(95, hour=13),
            scenario="unusual_disbursement",
            status=ApplicationStatus.APPROVED,
            sai=2100,
            program="B.S. Business Administration",
        )
        self.enrollment(org, stu, app, modality=Modality.HYBRID, credit_hours=12)
        self.db.flush()
        dest = self.destination()
        new_dest = self.destination()
        self.disbursement(org, stu, app, dest, fund=FundType.PELL_GRANT, amount=2890, when=self._term_day(-9))
        base = self._at(6, hour=10)
        self.disbursement(
            org,
            stu,
            app,
            new_dest,
            fund=FundType.INSTITUTIONAL_GRANT,
            amount=2400,
            when=base,
            destination_changed_at=base - timedelta(days=2),
        )
        self.disbursement(
            org,
            stu,
            app,
            new_dest,
            fund=FundType.DIRECT_UNSUBSIDIZED,
            amount=3000,
            when=base + timedelta(days=2),
            destination_changed_at=base - timedelta(days=2),
        )
        self.disbursement(
            org,
            stu,
            app,
            new_dest,
            fund=FundType.CREDIT_BALANCE_REFUND,
            amount=14850,
            when=base + timedelta(days=4),
            destination_changed_at=base - timedelta(days=2),
        )

    def scenario_coordinated_network(self) -> tuple[PaymentDestinationToken, PaymentDestinationToken]:
        """An 8-identity ring of online-only enrollments ('ghost students') sharing devices, IP, phones and accounts."""
        dest_a = self.destination(raw="0990000000000200001")
        dest_b = self.destination(raw="0990000000000200002")
        device, ip = "ring-device-shared-04", "198.51.100.23"
        shared_phone = self._phone()
        plan = ["lakeshore"] * 6 + ["pinecrest"] * 2
        for i, slug in enumerate(plan):
            org = self.orgs[slug]
            ident = self.identity(org, age=self.rng.choice([25, 28, 33, 36]))
            if i < 3:
                ident.phone = shared_phone
            stu = self.student(org, ident, consent=False)
            self.db.flush()
            app = self.application(
                org,
                stu,
                submitted_at=self._at(31 - i * 0.2, hour=self.rng.choice([1, 2, 3, 23])),
                device=device,
                ip=ip,
                scenario="coordinated_network",
                status=ApplicationStatus.APPROVED,
                requested=7395,
                sai=-1500,
                dependency="independent",
                intensity="half_time",
                program="A.A. General Studies" if slug == "lakeshore" else "Certificate in Industrial Maintenance",
                channel="online",
            )
            self.enrollment(
                org,
                stu,
                app,
                modality=Modality.ONLINE,
                credit_hours=6,
                attended=False,
                status=EnrollmentStatus.NEVER_ATTENDED,
            )
            self.db.flush()
            dest = dest_a if i % 2 == 0 else dest_b
            self.disbursement(org, stu, app, dest, fund=FundType.PELL_GRANT, amount=3697, when=self._term_day(-9))
            self.disbursement(
                org,
                stu,
                app,
                dest,
                fund=FundType.CREDIT_BALANCE_REFUND,
                amount=round(self.rng.uniform(2600, 3400), -1),
                when=self._term_day(21, hour=9),
                destination_changed_at=self._term_day(19, hour=2),
            )
        return dest_a, dest_b

    # ------------------------------------------------------------------ legitimate controls
    def control_siblings(self) -> None:
        """Two siblings: same household address and landline, different people. Should stay low risk."""
        org = self.orgs["northbridge"]
        address, phone = self._address(org), self._phone()
        last = self.rng.choice(LAST_NAMES)
        for age, days in ((19, 150), (21, 60)):
            stu = self.student(org, self.identity(org, age=age, last=last, address=address, phone=phone))
            self.db.flush()
            app = self.application(
                org,
                stu,
                submitted_at=self._at(days, hour=20),
                scenario="control_siblings",
                status=ApplicationStatus.APPROVED,
                dependency="dependent",
            )
            self.enrollment(org, stu, app, modality=Modality.IN_PERSON)
            self.db.flush()
            self.standard_disbursements(org, stu, app, self.destination(), refund=False)

    def control_dorm(self) -> None:
        """Five residents of the same residence hall share a campus mailing address."""
        org = self.orgs["northbridge"]
        hall = f"Harmon Residence Hall, 400 University Dr, {org.city}, {org.state}"
        for _ in range(5):
            stu = self.student(org, self.identity(org, age=18, address=hall))
            self.db.flush()
            app = self.application(
                org,
                stu,
                submitted_at=self._at(self.rng.uniform(80, 170), hour=16),
                scenario="control_dorm",
                status=ApplicationStatus.APPROVED,
                dependency="dependent",
            )
            self.enrollment(org, stu, app, modality=Modality.IN_PERSON)
            self.db.flush()
            self.standard_disbursements(org, stu, app, self.destination())

    def control_transfer(self) -> None:
        """Same person at two institutions in consecutive terms (completed, then enrolled): a normal transfer."""
        prior, current = self.orgs["lakeshore"], self.orgs["northbridge"]
        ident = self.identity(current, age=21)
        old = self.student(prior, ident)
        self.db.flush()
        prior_term = self.term_start - timedelta(days=210)
        self.enrollment(
            prior,
            old,
            None,
            status=EnrollmentStatus.COMPLETED,
            term=f"Spring {prior_term.year}",
            term_start=prior_term,
            credit_hours=15,
            modality=Modality.IN_PERSON,
        )
        new = self.student(current, ident)
        self.db.flush()
        app = self.application(
            current,
            new,
            submitted_at=self._at(120, hour=12),
            scenario="control_transfer",
            status=ApplicationStatus.APPROVED,
        )
        self.enrollment(current, new, app, modality=Modality.IN_PERSON, credit_hours=15)
        self.db.flush()
        self.standard_disbursements(current, new, app, self.destination())

    def control_bank_change(self) -> None:
        """A student updates their bank account, passes step-up verification, then receives a normal refund."""
        org = self.orgs["pinecrest"]
        stu = self.student(org, self.identity(org, age=23), consent=True)
        self.db.flush()
        app = self.application(
            org,
            stu,
            submitted_at=self._at(100, hour=10),
            scenario="control_bank_change",
            status=ApplicationStatus.APPROVED,
        )
        self.enrollment(org, stu, app, modality=Modality.IN_PERSON)
        self.db.flush()
        old, new = self.destination(), self.destination()
        self.disbursement(org, stu, app, old, fund=FundType.PELL_GRANT, amount=2600, when=self._term_day(-9))
        changed = self._term_day(5, hour=14)
        self.passed_verification(
            org, stu, app, when=changed + timedelta(minutes=12), trigger=VerificationTrigger.PAYMENT_DESTINATION_CHANGE
        )
        self.disbursement(
            org,
            stu,
            app,
            new,
            fund=FundType.CREDIT_BALANCE_REFUND,
            amount=1180,
            when=self._term_day(26),
            destination_changed_at=changed,
        )

    def control_high_need(self) -> None:
        """Independent adult learner with maximum Pell plus loans: large but entirely ordinary awards."""
        org = self.orgs["lakeshore"]
        stu = self.student(org, self.identity(org, age=34))
        self.db.flush()
        app = self.application(
            org,
            stu,
            submitted_at=self._at(110, hour=21),
            scenario="control_high_need",
            status=ApplicationStatus.APPROVED,
            requested=12500,
            sai=-1500,
            dependency="independent",
            intensity="full_time",
            program="A.A.S. Nursing",
        )
        self.enrollment(org, stu, app, modality=Modality.HYBRID, credit_hours=15)
        self.db.flush()
        dest = self.destination()
        self.disbursement(org, stu, app, dest, fund=FundType.PELL_GRANT, amount=3697, when=self._term_day(-9))
        self.disbursement(org, stu, app, dest, fund=FundType.DIRECT_SUBSIDIZED, amount=1750, when=self._term_day(-9))
        self.disbursement(org, stu, app, dest, fund=FundType.DIRECT_UNSUBSIDIZED, amount=3000, when=self._term_day(30))
        self.disbursement(
            org, stu, app, dest, fund=FundType.CREDIT_BALANCE_REFUND, amount=2950, when=self._term_day(33)
        )

    # ------------------------------------------------------------------ orchestration
    def run(self) -> GenerationSummary:
        self.baseline()
        ring_a, ring_b = self.scenario_coordinated_network()
        self.scenario_identity_impersonation(ring_b)
        self.scenario_duplicate_identity()
        self.scenario_shared_destination()
        self.scenario_unusual_disbursement()
        self.control_siblings()
        self.control_dorm()
        self.control_transfer()
        self.control_bank_change()
        self.control_high_need()
        self.db.flush()
        return self.summary
