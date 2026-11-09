from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Synthetic, TenantScoped, Timestamps, UUIDPrimaryKey


class ApplicationDocument(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "application_documents"
    __table_args__ = (
        Index("ix_application_documents_application", "application_id", "created_at"),
        # One pending/scanning replacement per original document. Historical documents remain unrestricted.
        Index(
            "uq_active_document_replacement",
            "replaces_document_id",
            unique=True,
            postgresql_where=text("status IN ('pending_scan', 'scanning')"),
            sqlite_where=text("status IN ('pending_scan', 'scanning')"),
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_aid_applications.id", ondelete="RESTRICT"))
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    original_filename: Mapped[str] = mapped_column(String(160))
    object_key: Mapped[str] = mapped_column(String(256), unique=True)
    object_version_id: Mapped[str | None] = mapped_column(String(128))
    detected_mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), index=True)
    review_status: Mapped[str] = mapped_column(String(32), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None]
    review_reason: Mapped[str | None] = mapped_column(String(1000))
    scanner_provider: Mapped[str | None] = mapped_column(String(40))
    scanned_at: Mapped[datetime | None]
    scan_attempts: Mapped[int] = mapped_column(default=0)
    scan_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    replaces_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_documents.id", ondelete="SET NULL")
    )


class DocumentScanJob(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    __tablename__ = "document_scan_jobs"
    __table_args__ = (Index("ix_document_scan_jobs_status_retry", "status", "next_attempt_at"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application_documents.id", ondelete="RESTRICT"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(40))


class DocumentObjectCleanup(UUIDPrimaryKey, Timestamps, TenantScoped, Synthetic, Base):
    """A durable, narrowly-scoped compensation record for an unlinked quarantine object."""

    __tablename__ = "document_object_cleanups"
    __table_args__ = (Index("ix_document_cleanup_status_retry", "status", "next_attempt_at"),)

    object_key: Mapped[str] = mapped_column(String(256), unique=True)
    object_version_id: Mapped[str | None] = mapped_column(String(128))
    checksum: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending_upload")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    error_code: Mapped[str | None] = mapped_column(String(40))
