"""Explainable risk assessments, their signals, alerts and detection runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey
from app.db.types import utcnow


class RiskAssessment(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
        Index("ix_risk_assessments_app_current", "application_id", "is_current"),
    )

    subject_type: Mapped[str] = mapped_column(String(16))  # "application" | "disbursement"
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="CASCADE")
    )
    disbursement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("disbursements.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float]
    level: Mapped[str] = mapped_column(String(10))
    method: Mapped[str] = mapped_column(String(80))
    rules_version: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(48))
    explanation: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(String(300))
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(default=dict)
    triggered_by: Mapped[str] = mapped_column(String(24))  # "detection_run" | "user" | "verification"
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_current: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    signals: Mapped[list[FraudSignal]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="FraudSignal.points.desc()",
    )


class FraudSignal(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "fraud_signals"

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_assessments.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(48), index=True)
    category: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(10))
    weight: Mapped[float]  # 0..1 strength fed into the noisy-OR combination
    points: Mapped[float]  # this signal's share of the final 0..100 score
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(default=dict)
    method: Mapped[str] = mapped_column(String(24))  # "rule" | "anomaly_model" | "graph" | "biometric"
    version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    assessment: Mapped[RiskAssessment] = relationship(back_populates="signals")


class Alert(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_org_status", "organization_id", "status"),)

    reference: Mapped[str] = mapped_column(String(24), unique=True)
    category: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    # Prevents duplicate open alerts for the same subject across detection runs.
    dedupe_key: Mapped[str] = mapped_column(String(120), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="SET NULL"), index=True
    )
    disbursement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("disbursements.id", ondelete="SET NULL"))
    verification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("identity_verifications.id", ondelete="SET NULL")
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risk_assessments.id", ondelete="SET NULL"))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("investigation_cases.id", ondelete="SET NULL"))
    risk_score: Mapped[float | None]
    triage_note: Mapped[str | None] = mapped_column(String(500))
    triaged_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    triaged_at: Mapped[datetime | None]


class DetectionRun(UUIDPrimaryKey, Base):
    __tablename__ = "detection_runs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str] = mapped_column(String(16))  # "inline" | "celery"
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    rules_version: Mapped[str] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(48))
    applications_scored: Mapped[int] = mapped_column(default=0)
    disbursements_scored: Mapped[int] = mapped_column(default=0)
    alerts_created: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
