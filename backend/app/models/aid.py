"""Financial aid applications, enrollment, payment destinations and disbursements."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey
from app.db.types import utcnow
from app.models.enums import ApplicationStatus, DisbursementStatus, ReviewStatus, VerificationStatus
from app.models.student import Student


class FinancialAidApplication(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "financial_aid_applications"
    __table_args__ = (
        CheckConstraint("requested_amount >= 0", name="requested_amount_non_negative"),
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="risk_score_range"),
        Index("ix_applications_org_risk", "organization_id", "risk_score"),
        Index("ix_applications_org_submitted", "organization_id", "submitted_at"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    award_year: Mapped[str] = mapped_column(String(9))
    submitted_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(20), default=ApplicationStatus.RECEIVED)
    dependency_status: Mapped[str] = mapped_column(String(16))
    enrollment_intensity: Mapped[str] = mapped_column(String(24))
    program: Mapped[str] = mapped_column(String(120))
    requested_amount: Mapped[Decimal]
    student_aid_index: Mapped[int]
    submission_channel: Mapped[str] = mapped_column(String(16))
    device_token: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_token: Mapped[str | None] = mapped_column(String(64), index=True)
    verification_status: Mapped[str] = mapped_column(String(20), default=VerificationStatus.NOT_REQUIRED)
    review_status: Mapped[str] = mapped_column(String(20), default=ReviewStatus.UNREVIEWED)
    risk_score: Mapped[float | None]
    risk_level: Mapped[str | None] = mapped_column(String(10), index=True)
    last_assessed_at: Mapped[datetime | None]
    # Tags records that belong to a documented demonstration scenario (see docs/demo-script.md).
    scenario_key: Mapped[str | None] = mapped_column(String(40), index=True)

    student: Mapped[Student] = relationship(lazy="joined")


class EnrollmentRecord(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "enrollment_records"
    __table_args__ = (CheckConstraint("credit_hours >= 0", name="credit_hours_non_negative"),)

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="SET NULL"), index=True
    )
    term: Mapped[str] = mapped_column(String(16))
    term_start: Mapped[date]
    program: Mapped[str] = mapped_column(String(120))
    credit_hours: Mapped[int]
    modality: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16))
    last_attendance_at: Mapped[datetime | None]


class PaymentDestinationToken(UUIDPrimaryKey, Base):
    """Platform-level pseudonym for a refund destination (bank account or prepaid card).

    Not tenant-scoped on purpose: the same destination receiving funds at several
    institutions is a key fraud signal. Only the HMAC token and a two-digit display
    suffix are kept; account and routing numbers are never stored.
    """

    __tablename__ = "payment_destination_tokens"

    token_value: Mapped[str] = mapped_column(String(64), unique=True)
    destination_type: Mapped[str] = mapped_column(String(16))
    display_suffix: Mapped[str] = mapped_column(String(4))
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    is_synthetic: Mapped[bool] = mapped_column(default=True)


class Disbursement(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "disbursements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_disbursements_org_date", "organization_id", "disbursed_at"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="SET NULL"), index=True
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payment_destination_tokens.id", ondelete="RESTRICT"), index=True
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    fund_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal]
    disbursed_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(String(16), default=DisbursementStatus.SCHEDULED)
    destination_changed_at: Mapped[datetime | None]
    risk_score: Mapped[float | None]
    risk_flags: Mapped[list[Any]] = mapped_column(default=list)
    hold_reason: Mapped[str | None] = mapped_column(String(500))
    held_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    held_at: Mapped[datetime | None]

    destination: Mapped[PaymentDestinationToken] = relationship(lazy="joined")
    student: Mapped[Student] = relationship(lazy="joined")
