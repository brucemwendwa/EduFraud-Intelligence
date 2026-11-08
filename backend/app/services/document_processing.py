"""Durable, idempotent and fail-closed document scan processing."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.db.types import utcnow
from app.models import ApplicationDocument, DocumentObjectCleanup, DocumentScanJob
from app.models.enums import AuditCategory, DocumentStatus
from app.services import audit
from app.services.document_scanner import ScanOutcome, ScanResult, get_document_scanner
from app.services.object_storage import get_object_storage

logger = logging.getLogger(__name__)


def _retry_delay(attempt: int) -> timedelta:
    settings = get_settings()
    return timedelta(seconds=min(settings.document_scan_retry_base_seconds * (2 ** max(attempt - 1, 0)), 3600))


def _claim_job(db, job_id: uuid.UUID) -> tuple[DocumentScanJob, ApplicationDocument, str] | None:
    """Claim exactly one due job. Row locking makes duplicate delivery harmless on PostgreSQL."""
    job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.id == job_id).with_for_update())
    if job is None or job.status not in {"queued", "retry"} or (job.next_attempt_at and job.next_attempt_at > utcnow()):
        return None
    doc = db.scalar(select(ApplicationDocument).where(ApplicationDocument.id == job.document_id).with_for_update())
    if doc is None or doc.status != DocumentStatus.PENDING_SCAN:
        job.status, job.finished_at = "cancelled", utcnow()
        db.commit()
        return None
    if job.attempts >= get_settings().document_scan_max_attempts:
        job.status, job.finished_at, job.error_code = "failed", utcnow(), "attempts_exhausted"
        doc.status = DocumentStatus.FAILED
        db.commit()
        return None
    job.status, job.started_at, job.attempts = "running", utcnow(), job.attempts + 1
    doc.status, doc.scan_attempts = DocumentStatus.SCANNING, job.attempts
    token = doc.scan_token or ""
    db.commit()
    return job, doc, token


def execute_scan(job_id: uuid.UUID) -> str | None:
    with SessionLocal() as db:
        claimed = _claim_job(db, job_id)
        if claimed is None:
            return
        job, doc, token = claimed
        try:
            before = get_object_storage().inspect(key=doc.object_key, version_id=doc.object_version_id)
            if before is None or before.checksum != doc.sha256:
                result = ScanResult(ScanOutcome.ERROR, "storage")
            else:
                result = get_document_scanner().scan(
                    object_key=doc.object_key,
                    object_version_id=doc.object_version_id,
                    checksum=doc.sha256,
                    scan_token=token,
                )
        except Exception:  # scanner/storage outage must fail closed
            logger.warning("Document scan unavailable for job %s", job_id)
            result = ScanResult(ScanOutcome.ERROR, "unavailable")
        db.refresh(job)
        db.refresh(doc)
        if job.status != "running" or doc.status != DocumentStatus.SCANNING or doc.scan_token != token:
            return
        doc.scanner_provider, doc.scanned_at = result.provider, utcnow()
        # Check again after scanning: a clean answer may only authorize the exact object inspected.
        try:
            after = get_object_storage().inspect(key=doc.object_key, version_id=doc.object_version_id)
        except Exception:
            after = None
        exact_object = after is not None and after.checksum == doc.sha256
        if result.outcome == ScanOutcome.CLEAN and not exact_object:
            result = ScanResult(ScanOutcome.ERROR, "storage")
        if result.outcome == ScanOutcome.CLEAN and exact_object:
            doc.status, job.status, job.finished_at = DocumentStatus.AVAILABLE, "completed", utcnow()
            if doc.replaces_document_id:
                old = db.get(ApplicationDocument, doc.replaces_document_id)
                if old is not None:
                    old.status = DocumentStatus.SUPERSEDED
        elif result.outcome == ScanOutcome.INFECTED:
            doc.status, job.status = DocumentStatus.REJECTED, "rejected"
            job.finished_at, job.error_code = utcnow(), "infected"
        elif job.attempts >= get_settings().document_scan_max_attempts:
            doc.status, job.status = DocumentStatus.FAILED, "failed"
            job.finished_at, job.error_code = utcnow(), result.outcome
        else:
            doc.status, job.status = DocumentStatus.PENDING_SCAN, "retry"
            job.next_attempt_at = utcnow() + _retry_delay(job.attempts)
            job.error_code = result.outcome
        audit.record(
            db,
            category=AuditCategory.APPLICATION,
            action=f"document.scan_{result.outcome}",
            organization_id=doc.organization_id,
            target_type="document",
            target_id=doc.id,
            details={"attempt": job.attempts, "provider": result.provider},
        )
        db.commit()
        return job.status


def execute_cleanup(cleanup_id: uuid.UUID) -> str | None:
    """Delete only an object still proven unreferenced by any document record."""
    with SessionLocal() as db:
        cleanup = db.scalar(
            select(DocumentObjectCleanup).where(DocumentObjectCleanup.id == cleanup_id).with_for_update()
        )
        if cleanup is None or cleanup.status not in {"pending_upload", "queued", "retry"}:
            return None
        if cleanup.next_attempt_at and cleanup.next_attempt_at > utcnow():
            return None
        referenced = db.scalar(
            select(ApplicationDocument.id).where(
                ApplicationDocument.object_key == cleanup.object_key,
                ApplicationDocument.object_version_id == cleanup.object_version_id,
            )
        )
        if referenced is not None:
            cleanup.status, cleanup.finished_at = "retained", utcnow()
            db.commit()
            return cleanup.status
        cleanup.attempts += 1
        try:
            get_object_storage().delete(key=cleanup.object_key, version_id=cleanup.object_version_id)
        except Exception:
            if cleanup.attempts >= get_settings().document_scan_max_attempts:
                cleanup.status, cleanup.finished_at, cleanup.error_code = "failed", utcnow(), "delete_failed"
            else:
                cleanup.status, cleanup.next_attempt_at, cleanup.error_code = (
                    "retry",
                    utcnow() + _retry_delay(cleanup.attempts),
                    "delete_failed",
                )
        else:
            cleanup.status, cleanup.finished_at, cleanup.error_code = "completed", utcnow(), None
        db.commit()
        return cleanup.status


def reconcile_document_scans() -> list[uuid.UUID]:
    """Recover expired leases and return due jobs for dispatch. Safe to call repeatedly."""
    with SessionLocal() as db:
        now = utcnow()
        lease_cutoff = now - timedelta(seconds=get_settings().document_scan_lease_seconds)
        abandoned = db.scalars(
            select(DocumentScanJob).where(
                DocumentScanJob.status == "running", DocumentScanJob.started_at < lease_cutoff
            )
        ).all()
        for job in abandoned:
            doc = db.get(ApplicationDocument, job.document_id)
            if doc and doc.status == DocumentStatus.SCANNING:
                doc.status = DocumentStatus.PENDING_SCAN
            job.status, job.next_attempt_at, job.error_code = "retry", now, "lease_expired"
        db.commit()
        return list(
            db.scalars(
                select(DocumentScanJob.id).where(
                    DocumentScanJob.status.in_(("queued", "retry")),
                    (DocumentScanJob.next_attempt_at.is_(None)) | (DocumentScanJob.next_attempt_at <= now),
                )
            )
        )


def reconcile_document_cleanups() -> list[uuid.UUID]:
    """Return due cleanup records; task claim logic makes duplicate scheduler delivery safe.

    A new intent is left alone for one lease period: until then its upload may still be in
    flight, and the document that will reference the object may not exist yet.
    """
    with SessionLocal() as db:
        now = utcnow()
        settled = now - timedelta(seconds=get_settings().document_scan_lease_seconds)
        return list(
            db.scalars(
                select(DocumentObjectCleanup.id).where(
                    DocumentObjectCleanup.status.in_(("pending_upload", "queued", "retry")),
                    DocumentObjectCleanup.created_at <= settled,
                    (DocumentObjectCleanup.next_attempt_at.is_(None)) | (DocumentObjectCleanup.next_attempt_at <= now),
                )
            )
        )
