from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DB, Principal, get_scoped_or_404, require
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import ApplicationDocument, DocumentObjectCleanup, DocumentScanJob, FinancialAidApplication, Student
from app.models.enums import AuditCategory, DocumentReviewStatus, DocumentStatus
from app.schemas.documents import DocumentCategory, DocumentOut, DocumentReview, DownloadUrl
from app.services import audit
from app.services.application_lifecycle import STUDENT_EDITABLE, staff_application_or_404
from app.services.object_storage import get_object_storage
from app.workers.document_jobs import enqueue_document_scan

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)
_TYPES = {
    b"%PDF-": ("application/pdf", ".pdf"),
    b"\xff\xd8\xff": ("image/jpeg", ".jpg"),
    b"\x89PNG\r\n\x1a\n": ("image/png", ".png"),
}


def _student(db: DB, principal: Principal) -> Student:
    if principal.user.student_id is None:
        raise ForbiddenError("This account is not linked to a student record.")
    student = db.get(Student, principal.user.student_id)
    if student is None or student.organization_id != principal.user.organization_id:
        raise ForbiddenError("This student record is unavailable.")
    return student


def _owned_app(db: DB, app_id: uuid.UUID, principal: Principal) -> FinancialAidApplication:
    student = _student(db, principal)
    app = db.get(FinancialAidApplication, app_id)
    if app is None or app.student_id != student.id or app.organization_id != student.organization_id:
        raise NotFoundError("Application not found.")
    return app


def _staff_document(db: DB, document_id: uuid.UUID, principal: Principal) -> ApplicationDocument:
    """A document on an application staff can see; evidence attached to an unsubmitted draft stays private."""
    doc = get_scoped_or_404(db, ApplicationDocument, document_id, principal, "Document")
    staff_application_or_404(db, doc.application_id, principal)
    return doc


def _out(doc: ApplicationDocument, *, staff: bool = False) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        application_id=doc.application_id,
        original_filename=doc.original_filename,
        detected_mime_type=doc.detected_mime_type,
        size_bytes=doc.size_bytes,
        category=doc.category,
        status=doc.status,
        scanner_provider=doc.scanner_provider,
        scanned_at=doc.scanned_at,
        review_status=doc.review_status,
        review_reason=doc.review_reason if staff or doc.review_status != DocumentReviewStatus.ACCEPTED else None,
        created_at=doc.created_at,
        reviewed_at=doc.reviewed_at,
        replaces_document_id=doc.replaces_document_id,
    )


def _validate(filename: str | None, body: bytes) -> tuple[str, str]:
    if (
        not filename
        or len(filename) > 160
        or PurePath(filename).name != filename
        or "\\" in filename
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
    ):
        raise ValidationFailedError("File name is invalid.")
    if not body:
        raise ValidationFailedError("The uploaded file is empty.")
    for signature, value in _TYPES.items():
        if body.startswith(signature):
            if len(body) <= len(signature):
                raise ValidationFailedError("The uploaded file is malformed.")
            mime, extension = value
            if not filename.lower().endswith(extension) and not (
                extension == ".jpg" and filename.lower().endswith(".jpeg")
            ):
                raise ValidationFailedError("File extension does not match its detected format.")
            return mime, extension
    raise ValidationFailedError("Only PDF, JPEG and PNG documents are accepted.")


async def _create_document(
    *,
    app: FinancialAidApplication,
    request: Request,
    db: DB,
    principal: Principal,
    category: DocumentCategory,
    file: UploadFile,
    replaces_document_id: uuid.UUID | None = None,
) -> tuple[ApplicationDocument, DocumentScanJob]:
    """Store the object first, then atomically persist its quarantine metadata and job.

    An object that cannot be linked to a database record is deleted best-effort; no
    database document is ever created before its object upload succeeds.
    """
    body = await file.read(get_settings().document_max_upload_bytes + 1)
    if len(body) > get_settings().document_max_upload_bytes:
        raise ValidationFailedError("The file exceeds the permitted upload size.")
    mime, extension = _validate(file.filename, body)
    checksum = hashlib.sha256(body).hexdigest()
    key = f"quarantine/{app.organization_id}/{app.id}/{secrets.token_urlsafe(24)}{extension}"
    # Commit a cleanup intent before storage I/O. If the request crashes at any later
    # point, reconciliation can delete only this opaque, unreferenced quarantine key.
    cleanup = DocumentObjectCleanup(organization_id=app.organization_id, object_key=key, status="pending_upload")
    db.add(cleanup)
    db.commit()
    storage = get_object_storage()
    try:
        stored = storage.put(key=key, body=body, content_type=mime, checksum=checksum)
    except Exception:
        # A provider timeout can be ambiguous: retain the cleanup intent rather than
        # assuming an object was not written.
        cleanup.status, cleanup.error_code = "queued", "upload_uncertain"
        db.commit()
        raise
    cleanup.object_version_id, cleanup.checksum, cleanup.status = stored.version_id, stored.checksum, "queued"
    db.commit()
    doc = ApplicationDocument(
        organization_id=app.organization_id,
        application_id=app.id,
        uploaded_by_id=principal.user.id,
        original_filename=file.filename,
        object_key=key,
        object_version_id=stored.version_id,
        detected_mime_type=mime,
        size_bytes=len(body),
        sha256=checksum,
        category=category,
        status=DocumentStatus.PENDING_SCAN,
        review_status=DocumentReviewStatus.PENDING,
        scan_token=secrets.token_hex(32),
        replaces_document_id=replaces_document_id,
    )
    try:
        db.add(doc)
        db.flush()
        job = DocumentScanJob(organization_id=app.organization_id, document_id=doc.id, status="queued")
        db.add(job)
        audit.record(
            db,
            category=AuditCategory.APPLICATION,
            action="document.replace" if replaces_document_id else "document.upload",
            actor=principal.user,
            organization_id=app.organization_id,
            target_type="document",
            target_id=doc.id,
            target_ref=app.reference,
            details={"category": category, "size_bytes": len(body)},
            request=request,
        )
        cleanup.status, cleanup.finished_at = "retained", utcnow()
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise ValidationFailedError("The document could not be recorded. Please retry.") from exc
    db.refresh(doc)
    db.refresh(job)
    return doc, job


@router.get("/student-applications/{application_id}/documents", response_model=list[DocumentOut])
def list_student_documents(
    application_id: uuid.UUID, db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]
) -> list[DocumentOut]:
    app = _owned_app(db, application_id, principal)
    return [
        _out(d)
        for d in db.scalars(
            select(ApplicationDocument)
            .where(ApplicationDocument.application_id == app.id)
            .order_by(ApplicationDocument.created_at.desc())
        )
    ]


@router.post("/student-applications/{application_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    application_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
    category: DocumentCategory = Form(),
    file: UploadFile = File(),
) -> DocumentOut:
    app = _owned_app(db, application_id, principal)
    if app.status not in {s.value for s in STUDENT_EDITABLE}:
        raise ConflictError("Documents can only be uploaded while this application is editable.")
    doc, job = await _create_document(
        app=app, request=request, db=db, principal=principal, category=category, file=file
    )
    enqueue_document_scan(job.id, background)
    return _out(doc)


@router.post("/student-documents/{document_id}/replace", response_model=DocumentOut, status_code=201)
async def replace_document(
    document_id: uuid.UUID,
    request: Request,
    background: BackgroundTasks,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
    category: DocumentCategory = Form(),
    file: UploadFile = File(),
) -> DocumentOut:
    old = db.get(ApplicationDocument, document_id)
    if old is None or _owned_app(db, old.application_id, principal).organization_id != old.organization_id:
        raise NotFoundError("Document not found.")
    app = _owned_app(db, old.application_id, principal)
    can_replace = app.status in {s.value for s in STUDENT_EDITABLE} or (
        old.review_status == DocumentReviewStatus.REPLACEMENT_REQUESTED
    )
    if not can_replace or old.status == DocumentStatus.SUPERSEDED:
        raise ConflictError("This document cannot be replaced at this time.")
    active_replacement = db.scalar(
        select(ApplicationDocument.id).where(
            ApplicationDocument.replaces_document_id == old.id,
            ApplicationDocument.status.in_((DocumentStatus.PENDING_SCAN, DocumentStatus.SCANNING)),
        )
    )
    if active_replacement is not None:
        raise ConflictError("A replacement document is already awaiting verification.")
    new, job = await _create_document(
        app=app,
        request=request,
        db=db,
        principal=principal,
        category=category,
        file=file,
        replaces_document_id=old.id,
    )
    # Dispatch happens only after the replacement relationship has committed.
    enqueue_document_scan(job.id, background)
    return _out(new)


@router.post("/student-documents/{document_id}/download", response_model=DownloadUrl)
def student_download(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))],
) -> DownloadUrl:
    doc = db.get(ApplicationDocument, document_id)
    if doc is None or _owned_app(db, doc.application_id, principal).organization_id != doc.organization_id:
        raise NotFoundError("Document not found.")
    if doc.status != DocumentStatus.AVAILABLE:
        raise ConflictError("This document is not available for download.")
    url = get_object_storage().download_url(
        key=doc.object_key, filename=doc.original_filename, content_type=doc.detected_mime_type
    )
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="document.download",
        actor=principal.user,
        organization_id=doc.organization_id,
        target_type="document",
        target_id=doc.id,
        target_ref=None,
        request=request,
    )
    db.commit()
    return DownloadUrl(url=url, expires_in_seconds=get_settings().s3_presigned_url_ttl_seconds)


@router.post("/documents/{document_id}/download", response_model=DownloadUrl)
def staff_download(
    document_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.APPLICATIONS_READ))],
) -> DownloadUrl:
    """Issue an attachment URL only after a tenant-scoped staff authorization check."""
    doc = _staff_document(db, document_id, principal)
    if doc.status != DocumentStatus.AVAILABLE:
        raise ConflictError("This document is not available for download.")
    url = get_object_storage().download_url(
        key=doc.object_key, filename=doc.original_filename, content_type=doc.detected_mime_type
    )
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="document.download",
        actor=principal.user,
        organization_id=doc.organization_id,
        target_type="document",
        target_id=doc.id,
        request=request,
    )
    db.commit()
    return DownloadUrl(url=url, expires_in_seconds=get_settings().s3_presigned_url_ttl_seconds)


@router.get("/applications/{application_id}/documents", response_model=list[DocumentOut])
def list_staff_documents(
    application_id: uuid.UUID, db: DB, principal: Annotated[Principal, Depends(require(P.APPLICATIONS_READ))]
) -> list[DocumentOut]:
    app = staff_application_or_404(db, application_id, principal)
    return [
        _out(d, staff=True)
        for d in db.scalars(
            select(ApplicationDocument)
            .where(ApplicationDocument.application_id == app.id)
            .order_by(ApplicationDocument.created_at.desc())
        )
    ]


@router.patch("/documents/{document_id}/review", response_model=DocumentOut)
def review_document(
    document_id: uuid.UUID,
    body: DocumentReview,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.APPLICATIONS_REVIEW))],
) -> DocumentOut:
    doc = _staff_document(db, document_id, principal)
    if doc.status != DocumentStatus.AVAILABLE:
        raise ConflictError("Only scan-cleared documents can be reviewed.")
    doc.review_status, doc.review_reason, doc.reviewer_id, doc.reviewed_at = (
        body.decision,
        body.reason,
        principal.user.id,
        utcnow(),
    )
    audit.record(
        db,
        category=AuditCategory.APPLICATION,
        action=f"document.review_{body.decision}",
        actor=principal.user,
        organization_id=doc.organization_id,
        target_type="document",
        target_id=doc.id,
        details={"decision": body.decision, "reason": body.reason, "category": doc.category},
        request=request,
    )
    db.commit()
    db.refresh(doc)
    return _out(doc, staff=True)
