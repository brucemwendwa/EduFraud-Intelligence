"""Student ID-linked financial aid accounts, ID cards, card transactions, devices and security events.

Funds are never held by the card or by EduShield. They sit in an account operated by a
regulated banking or payment-provider partner; the university ID card is only the credential
used to access them. EduShield keeps pseudonymous references (HMAC tokens) to provider
accounts, cards, devices and sessions, plus the event data it needs to monitor risk. It never
stores card numbers, provider account numbers, PINs or other payment credentials.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey
from app.models.enums import AccountStatus, CardStatus, DeviceTrust, TransactionReview, TransactionStatus
from app.models.student import Student


class StudentFinancialAccount(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "student_financial_accounts"
    __table_args__ = (
        UniqueConstraint("student_id"),
        Index("ix_sfa_org_status", "organization_id", "status"),
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="risk_score_range"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    provider_key: Mapped[str] = mapped_column(String(48))
    provider_mode: Mapped[str] = mapped_column(String(16))  # "sandbox" until a licensed partner is connected
    # HMAC of the provider's own account identifier. Lets provider webhooks be matched without storing it.
    provider_account_token: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), default=AccountStatus.ACTIVE)
    status_reason: Mapped[str | None] = mapped_column(String(300))
    status_changed_at: Mapped[datetime | None]
    status_changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Step-up hold on sensitive changes (payout redirection, credential changes, card replacement).
    # Everyday card spending is not affected; only a person or the provider can suspend an account.
    sensitive_actions_restricted: Mapped[bool] = mapped_column(default=False)
    restriction_reason: Mapped[str | None] = mapped_column(String(300))
    restricted_at: Mapped[datetime | None]
    available_balance: Mapped[Decimal | None]  # as last reported by the provider; never computed here
    balance_as_of: Mapped[datetime | None]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    study_mode: Mapped[str] = mapped_column(String(20))
    home_city: Mapped[str] = mapped_column(String(80))
    home_country: Mapped[str] = mapped_column(String(2))
    opened_at: Mapped[datetime]
    last_transaction_at: Mapped[datetime | None]
    risk_score: Mapped[float | None]
    risk_level: Mapped[str | None] = mapped_column(String(10), index=True)
    last_assessed_at: Mapped[datetime | None]
    scenario_key: Mapped[str | None] = mapped_column(String(40), index=True)

    student: Mapped[Student] = relationship(lazy="joined")


class StudentIDCard(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "student_id_cards"
    __table_args__ = (
        # A student holds at most one active card at a time.
        Index(
            "uq_student_id_cards_one_active",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index("ix_cards_org_status", "organization_id", "status"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_financial_accounts.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    # HMAC of the card serial; only the last four characters are kept for display.
    card_token: Mapped[str] = mapped_column(String(64), unique=True)
    display_suffix: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(24), default=CardStatus.ACTIVE)
    issued_at: Mapped[datetime]
    activated_at: Mapped[datetime | None]
    expires_on: Mapped[date]
    reported_lost_at: Mapped[datetime | None]
    report_channel: Mapped[str | None] = mapped_column(String(24))
    blocked_at: Mapped[datetime | None]
    block_confirmation: Mapped[str | None] = mapped_column(String(48))  # provider acknowledgement reference
    replacement_requested_at: Mapped[datetime | None]
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("student_id_cards.id", ondelete="SET NULL"))
    scenario_key: Mapped[str | None] = mapped_column(String(40))

    student: Mapped[Student] = relationship(lazy="joined")


class Transaction(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    """A card or account transaction event received from the payment provider."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="risk_score_range"),
        Index("ix_transactions_org_time", "organization_id", "occurred_at"),
        Index("ix_transactions_account_time", "account_id", "occurred_at"),
        Index("ix_transactions_org_risk", "organization_id", "risk_level"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("student_financial_accounts.id", ondelete="RESTRICT"))
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("student_id_cards.id", ondelete="SET NULL"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    provider_event_id: Mapped[str] = mapped_column(String(64), unique=True)  # webhook idempotency key
    transaction_type: Mapped[str] = mapped_column(String(24))  # purchase | atm_withdrawal | transfer_out
    channel: Mapped[str] = mapped_column(String(16))  # card_present | online | atm | transfer
    merchant_name: Mapped[str] = mapped_column(String(120))
    merchant_category: Mapped[str] = mapped_column(String(32), index=True)
    merchant_token: Mapped[str | None] = mapped_column(String(64), index=True)
    destination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_destination_tokens.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    occurred_at: Mapped[datetime]
    # Coarse, merchant-derived location reported with the authorised transaction (never device GPS).
    location_city: Mapped[str | None] = mapped_column(String(80))
    location_country: Mapped[str | None] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(16), default=TransactionStatus.APPROVED)
    decline_reason: Mapped[str | None] = mapped_column(String(160))
    risk_score: Mapped[float | None]
    risk_level: Mapped[str | None] = mapped_column(String(10))
    risk_indicators: Mapped[list[Any]] = mapped_column(default=list)
    review_status: Mapped[str] = mapped_column(String(16), default=TransactionReview.UNREVIEWED)
    review_note: Mapped[str | None] = mapped_column(String(500))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None]
    scenario_key: Mapped[str | None] = mapped_column(String(40), index=True)

    student: Mapped[Student] = relationship(lazy="joined")


class Device(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    """A device fingerprint seen signing in to a student's account (keyed hash only)."""

    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("student_id", "device_token"),)

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    device_token: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(24))
    trust_status: Mapped[str] = mapped_column(String(16), default=DeviceTrust.UNFAMILIAR)
    trust_reason: Mapped[str | None] = mapped_column(String(300))
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    # Registered shared devices (e.g. library kiosks) never count as cross-account sharing.
    is_shared_kiosk: Mapped[bool] = mapped_column(default=False)

    student: Mapped[Student] = relationship(lazy="joined")


class SecurityEvent(UUIDPrimaryKey, TenantScoped, Synthetic, Base):
    """An authorised account-security event from the identity or payment provider, or an officer action."""

    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_org_time", "organization_id", "occurred_at"),
        Index("ix_security_events_student_time", "student_id", "occurred_at"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_financial_accounts.id", ondelete="SET NULL"), index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("student_id_cards.id", ondelete="SET NULL"))
    destination_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_destination_tokens.id", ondelete="RESTRICT"), index=True
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    source: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))  # success | failure | challenged | blocked | recorded
    occurred_at: Mapped[datetime]
    session_token: Mapped[str | None] = mapped_column(String(64))
    ip_token: Mapped[str | None] = mapped_column(String(64))
    location_city: Mapped[str | None] = mapped_column(String(80))
    location_country: Mapped[str | None] = mapped_column(String(2))
    risk_score: Mapped[float | None]
    risk_level: Mapped[str | None] = mapped_column(String(10))
    risk_indicators: Mapped[list[Any]] = mapped_column(default=list)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    scenario_key: Mapped[str | None] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime]

    student: Mapped[Student] = relationship(lazy="joined")
    device: Mapped[Device | None] = relationship(lazy="joined")
