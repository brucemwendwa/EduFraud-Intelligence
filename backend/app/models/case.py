"""Investigation cases, their evidence and append-only notes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScoped, Timestamps, UUIDPrimaryKey
from app.db.types import utcnow
from app.models.enums import CaseFinding, CasePriority, CaseStatus
from app.models.identity import User


class InvestigationCase(UUIDPrimaryKey, Timestamps, TenantScoped, Base):
    __tablename__ = "investigation_cases"

    reference: Mapped[str] = mapped_column(String(24), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_aid_applications.id", ondelete="SET NULL"), index=True
    )
    fraud_category: Mapped[str] = mapped_column(String(32))
    priority: Mapped[str] = mapped_column(String(10), default=CasePriority.MEDIUM)
    status: Mapped[str] = mapped_column(String(16), default=CaseStatus.NEW, index=True)
    risk_score_at_open: Mapped[float | None]
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolution: Mapped[str | None] = mapped_column(String(32))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]
    due_at: Mapped[datetime | None]
    # Keeps suspicion and findings distinct: suspicious_activity -> suspected_fraud -> confirmed_fraud,
    # or not_substantiated. Only a recorded human decision moves it.
    finding: Mapped[str] = mapped_column(String(24), default=CaseFinding.SUSPICIOUS_ACTIVITY)

    assigned_to: Mapped[User | None] = relationship(foreign_keys=[assigned_to_id], lazy="joined")
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id], lazy="joined")
    evidence: Mapped[list[CaseEvidence]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseEvidence.created_at"
    )
    notes: Mapped[list[CaseNote]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseNote.created_at"
    )
    decisions: Mapped[list[CaseDecision]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseDecision.decided_at"
    )


class CaseEvidence(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "case_evidence"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigation_cases.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(24))
    ref_id: Mapped[uuid.UUID | None]
    ref_label: Mapped[str | None] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(default=dict)
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    case: Mapped[InvestigationCase] = relationship(back_populates="evidence")
    added_by: Mapped[User | None] = relationship(lazy="joined")


class CaseNote(UUIDPrimaryKey, TenantScoped, Base):
    """Append-only: the API exposes no update or delete for investigative notes."""

    __tablename__ = "case_notes"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigation_cases.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    case: Mapped[InvestigationCase] = relationship(back_populates="notes")
    author: Mapped[User | None] = relationship(lazy="joined")


class CaseDecision(UUIDPrimaryKey, TenantScoped, Base):
    """A consequential human decision on a case: who decided, when, what, and why. Append-only."""

    __tablename__ = "case_decisions"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("investigation_cases.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(16))  # escalate | resolve | reopen | close
    outcome: Mapped[str | None] = mapped_column(String(32))  # resolution outcome when decision == resolve
    finding: Mapped[str] = mapped_column(String(24))  # finding level after this decision
    from_status: Mapped[str] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    justification: Mapped[str] = mapped_column(Text)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime] = mapped_column(default=utcnow)

    case: Mapped[InvestigationCase] = relationship(back_populates="decisions")
    decided_by: Mapped[User | None] = relationship(lazy="joined")
