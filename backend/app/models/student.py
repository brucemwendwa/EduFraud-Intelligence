"""Students and their pseudonymous identity tokens. No raw identifiers are stored."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey
from app.db.types import EncryptedString, utcnow


class Student(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("organization_id", "student_ref"),)

    student_ref: Mapped[str] = mapped_column(String(24))
    # Names are encrypted at rest and masked in API responses unless a reveal is justified + audited.
    first_name: Mapped[str] = mapped_column(EncryptedString())
    last_name: Mapped[str] = mapped_column(EncryptedString())
    # Data minimization: birth year only (full DOB exists solely as an HMAC token).
    birth_year: Mapped[int]
    state_of_residence: Mapped[str] = mapped_column(String(2))
    biometric_consent: Mapped[bool] = mapped_column(default=False)
    biometric_consent_at: Mapped[datetime | None]
    # Opaque handle to a template held by the (simulated) verification provider — never the template itself.
    biometric_reference_id: Mapped[str | None] = mapped_column(String(64))

    identity_tokens: Mapped[list[StudentIdentityToken]] = relationship(
        back_populates="student", cascade="all, delete-orphan", lazy="selectin"
    )


class StudentIdentityToken(UUIDPrimaryKey, TenantScoped, Base):
    __tablename__ = "student_identity_tokens"
    __table_args__ = (
        UniqueConstraint("student_id", "token_type"),
        Index("ix_identity_tokens_type_value", "token_type", "token_value"),
    )

    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    token_type: Mapped[str] = mapped_column(String(16))
    token_value: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    student: Mapped[Student] = relationship(back_populates="identity_tokens")
