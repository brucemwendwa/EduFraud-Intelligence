"""Identity verification attempts. Only scores and reason codes are persisted — never images or templates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey
from app.db.types import utcnow
from app.models.identity import User
from app.models.student import Student


class IdentityVerification(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "identity_verifications"

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="SET NULL"), index=True
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    trigger: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(48))
    provider_mode: Mapped[str] = mapped_column(String(16))  # "simulation" | "live"
    status: Mapped[str] = mapped_column(String(16), index=True)

    document_result: Mapped[str] = mapped_column(String(24))
    document_type: Mapped[str | None] = mapped_column(String(32))
    face_match_score: Mapped[float | None]
    liveness_score: Mapped[float | None]
    liveness_result: Mapped[str] = mapped_column(String(24))
    pad_result: Mapped[str] = mapped_column(String(24))
    pad_attack_type: Mapped[str | None] = mapped_column(String(32))
    quality_flags: Mapped[list[Any]] = mapped_column(default=list)
    risk_indicators: Mapped[list[Any]] = mapped_column(default=list)
    recommended_action: Mapped[str] = mapped_column(String(300))
    # Simulation only: which synthetic test sample was presented.
    sample_key: Mapped[str | None] = mapped_column(String(48))
    session_context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    initiated_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None]

    student: Mapped[Student] = relationship(lazy="joined")


class VerificationRequest(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    """A request for a student to re-verify their identity, followed from notification to decision.

    Two pathways: on campus (the student visits the designated verification office) and remote
    (secure video, document check, provider liveness, alternatives, or embassy-assisted where a
    formal arrangement exists). Officers record every step; a person records the outcome.
    """

    __tablename__ = "verification_requests"
    __table_args__ = (Index("ix_verification_requests_org_status", "organization_id", "status"),)

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="RESTRICT"), index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("student_financial_accounts.id", ondelete="SET NULL"), index=True
    )
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("student_id_cards.id", ondelete="SET NULL"))
    alert_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("investigation_cases.id", ondelete="SET NULL"))
    identity_verification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity_verifications.id", ondelete="SET NULL")
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True)
    trigger: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(500))
    pathway: Mapped[str] = mapped_column(String(16))
    method: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notified_at: Mapped[datetime | None]
    due_at: Mapped[datetime | None]
    appointment_at: Mapped[datetime | None]
    location_note: Mapped[str | None] = mapped_column(String(160))
    outcome_reason: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None]
    access_restored: Mapped[bool] = mapped_column(default=False)
    scenario_key: Mapped[str | None] = mapped_column(String(40))

    student: Mapped[Student] = relationship(lazy="joined")
    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id], lazy="joined")
    events: Mapped[list[VerificationRequestEvent]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="VerificationRequestEvent.created_at",
        lazy="selectin",
    )


class VerificationRequestEvent(UUIDPrimaryKey, TenantScoped, Base):
    """Append-only timeline of a verification request."""

    __tablename__ = "verification_request_events"

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_requests.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(40))
    status_after: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    request: Mapped[VerificationRequest] = relationship(back_populates="events")
