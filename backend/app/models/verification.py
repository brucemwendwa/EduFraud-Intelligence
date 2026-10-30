"""Identity verification attempts. Only scores and reason codes are persisted — never images or templates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey
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
