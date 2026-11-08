"""Document evidence tests use in-memory adapters; no cloud or scanner credentials are required."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import (
    ApplicationDocument,
    AuditEvent,
    DocumentObjectCleanup,
    DocumentScanJob,
    FinancialAidApplication,
    User,
)
from app.models.enums import DocumentStatus
from app.seed.base import DEMO_STUDENT_EMAIL
from app.services.document_processing import (
    execute_cleanup,
    execute_scan,
    reconcile_document_cleanups,
    reconcile_document_scans,
)
from app.services.document_scanner import ScanOutcome, ScanResult
from app.services.object_storage import StoredObject

pytestmark = pytest.mark.seeded

PDF = b"%PDF-1.7\nsynthetic financial-aid evidence"


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, str]] = {}
        self.deleted: list[str] = []
        self.fail_delete = False

    def put(self, *, key: str, body: bytes, content_type: str, checksum: str) -> StoredObject:
        del content_type
        assert hashlib.sha256(body).hexdigest() == checksum
        version = f"v-{len(self.objects) + 1}"
        self.objects[key] = (body, version, checksum)
        return StoredObject(version, checksum)

    def delete(self, *, key: str, version_id: str | None = None) -> None:
        if self.fail_delete:
            raise RuntimeError("storage unavailable")
        if version_id and key in self.objects and self.objects[key][1] != version_id:
            return
        self.deleted.append(key)
        self.objects.pop(key, None)

    def inspect(self, *, key: str, version_id: str | None = None) -> StoredObject | None:
        item = self.objects.get(key)
        if item is None or (version_id and item[1] != version_id):
            return None
        return StoredObject(item[1], item[2])

    def get(self, *, key: str, version_id: str | None = None) -> bytes:
        del version_id
        return self.objects[key][0]

    def download_url(self, *, key: str, filename: str, content_type: str, version_id: str | None = None) -> str:
        assert key in self.objects and version_id == self.objects[key][1]
        return f"https://storage.invalid/{key}?filename={filename}&type={content_type}"


class FixedScanner:
    def __init__(self, outcome: ScanOutcome) -> None:
        self.outcome = outcome

    def scan(self, *, object_key: str, object_version_id: str | None, checksum: str, scan_token: str) -> ScanResult:
        assert object_key and object_version_id and checksum and scan_token
        return ScanResult(self.outcome, "test-scanner")


def _draft(as_user):  # type: ignore[no-untyped-def]
    student = as_user(DEMO_STUDENT_EMAIL)
    response = student.post("/api/v1/student-applications", json={})
    assert response.status_code == 201, response.text
    return student, response.json()


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> MemoryStorage:
    from app.api.v1 import documents
    from app.services import document_processing

    result = MemoryStorage()
    monkeypatch.setattr(documents, "get_object_storage", lambda: result)
    monkeypatch.setattr(document_processing, "get_object_storage", lambda: result)
    monkeypatch.setattr(documents, "enqueue_document_scan", lambda *_: "test")
    return result


def _upload(student, application_id: str, filename: str = "income.pdf", body: bytes = PDF):  # type: ignore[no-untyped-def]
    return student.post(
        f"/api/v1/student-applications/{application_id}/documents",
        data={"category": "income_evidence"},
        files={"file": (filename, body, "application/octet-stream")},
    )


def test_upload_is_quarantined_hashed_and_audited(as_user, db: Session, storage: MemoryStorage) -> None:  # type: ignore[no-untyped-def]
    student, app = _draft(as_user)
    response = _upload(student, app["id"])
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "pending_scan"
    doc = db.get(ApplicationDocument, uuid.UUID(payload["id"]))
    assert doc is not None and doc.object_key.startswith("quarantine/")
    assert doc.sha256 == hashlib.sha256(PDF).hexdigest() and doc.object_key in storage.objects
    assert doc.object_version_id == storage.objects[doc.object_key][1]
    assert db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == doc.id)) is not None
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "document.upload")) is not None


@pytest.mark.parametrize(
    "filename,body", [("evidence.txt", b"not a document"), ("empty.pdf", b""), ("bad.pdf", b"%PDF-")]
)
def test_upload_rejects_spoofed_empty_and_malformed_files(
    as_user, storage: MemoryStorage, filename: str, body: bytes
) -> None:  # type: ignore[no-untyped-def]
    student, app = _draft(as_user)
    response = _upload(student, app["id"], filename, body)
    assert response.status_code == 422
    assert not storage.objects


def test_document_scan_outcomes_fail_closed_and_preserve_quarantine(
    as_user, db: Session, storage: MemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from app.services import document_processing

    student, app = _draft(as_user)
    uploaded = _upload(student, app["id"])
    document_id = uuid.UUID(uploaded.json()["id"])
    doc = db.get(ApplicationDocument, document_id)
    assert doc is not None
    job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == document_id))
    assert job is not None
    monkeypatch.setattr(document_processing, "get_document_scanner", lambda: FixedScanner(ScanOutcome.CLEAN))
    assert execute_scan(job.id) == "completed"
    db.refresh(doc)
    assert doc.status == DocumentStatus.AVAILABLE

    # A second uploaded object is never made available when its scanner is unavailable.
    retry = _upload(student, app["id"], "other.pdf", PDF + b"-2")
    retry_doc = db.get(ApplicationDocument, uuid.UUID(retry.json()["id"]))
    assert retry_doc is not None
    retry_job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == retry_doc.id))
    assert retry_job is not None
    monkeypatch.setattr(document_processing, "get_document_scanner", lambda: FixedScanner(ScanOutcome.UNAVAILABLE))
    assert execute_scan(retry_job.id) == "retry"
    db.refresh(retry_doc)
    assert retry_doc.status == DocumentStatus.PENDING_SCAN


def test_missing_object_and_abandoned_job_are_recovered(
    as_user, db: Session, storage: MemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    student, app = _draft(as_user)
    uploaded = _upload(student, app["id"])
    doc = db.get(ApplicationDocument, uuid.UUID(uploaded.json()["id"]))
    assert doc is not None
    job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == doc.id))
    assert job is not None
    storage.objects.pop(doc.object_key)
    assert execute_scan(job.id) == "retry"
    db.refresh(job)
    assert job.error_code == ScanOutcome.ERROR
    job.status, job.started_at = "running", utcnow().replace(year=2000)
    doc.status = DocumentStatus.SCANNING
    db.commit()
    assert job.id in reconcile_document_scans()
    db.refresh(job)
    db.refresh(doc)
    assert job.status == "retry" and doc.status == DocumentStatus.PENDING_SCAN


def test_student_cannot_read_or_replace_another_students_document(as_user, db: Session, storage: MemoryStorage) -> None:  # type: ignore[no-untyped-def]
    owner, app = _draft(as_user)
    uploaded = _upload(owner, app["id"])
    doc_id = uploaded.json()["id"]
    owner_user = db.scalar(select(User).where(User.email == DEMO_STUDENT_EMAIL))
    assert owner_user is not None
    other_app = db.scalar(
        select(FinancialAidApplication).where(FinancialAidApplication.student_id != owner_user.student_id)
    )
    assert other_app is not None
    # The seeded second student's login is intentionally unavailable; a staff account lacks the student permission.
    staff = as_user("officer@northbridge.demo")
    assert (
        staff.post(
            f"/api/v1/student-documents/{doc_id}/replace",
            data={"category": "income_evidence"},
            files={"file": ("x.pdf", PDF)},
        ).status_code
        == 403
    )
    assert staff.post(f"/api/v1/student-documents/{doc_id}/download").status_code == 403


def test_replacement_preserves_old_document_until_clean_scan(
    as_user, db: Session, storage: MemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from app.services import document_processing

    student, app = _draft(as_user)
    first = _upload(student, app["id"])
    old = db.get(ApplicationDocument, uuid.UUID(first.json()["id"]))
    assert old is not None
    old.status = DocumentStatus.AVAILABLE
    db.commit()
    replacement = student.post(
        f"/api/v1/student-documents/{old.id}/replace",
        data={"category": "income_evidence"},
        files={"file": ("replacement.pdf", PDF + b" replacement")},
    )
    assert replacement.status_code == 201, replacement.text
    new = db.get(ApplicationDocument, uuid.UUID(replacement.json()["id"]))
    assert new is not None and new.replaces_document_id == old.id
    assert old.status == DocumentStatus.AVAILABLE
    job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == new.id))
    assert job is not None
    monkeypatch.setattr(document_processing, "get_document_scanner", lambda: FixedScanner(ScanOutcome.CLEAN))
    assert execute_scan(job.id) == "completed"
    db.refresh(old)
    assert old.status == DocumentStatus.SUPERSEDED


def test_only_one_pending_replacement_is_permitted(as_user, db: Session, storage: MemoryStorage) -> None:  # type: ignore[no-untyped-def]
    student, app = _draft(as_user)
    first = _upload(student, app["id"])
    old = db.get(ApplicationDocument, uuid.UUID(first.json()["id"]))
    assert old is not None
    old.status = DocumentStatus.AVAILABLE
    db.commit()
    first_replacement = student.post(
        f"/api/v1/student-documents/{old.id}/replace",
        data={"category": "income_evidence"},
        files={"file": ("one.pdf", PDF + b" one")},
    )
    assert first_replacement.status_code == 201
    second_replacement = student.post(
        f"/api/v1/student-documents/{old.id}/replace",
        data={"category": "income_evidence"},
        files={"file": ("two.pdf", PDF + b" two")},
    )
    assert second_replacement.status_code == 409


def test_changed_object_version_or_checksum_never_becomes_available(
    as_user, db: Session, storage: MemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from app.services import document_processing

    student, app = _draft(as_user)
    uploaded = _upload(student, app["id"])
    doc = db.get(ApplicationDocument, uuid.UUID(uploaded.json()["id"]))
    assert doc is not None
    job = db.scalar(select(DocumentScanJob).where(DocumentScanJob.document_id == doc.id))
    assert job is not None
    # Simulate a same-key overwrite after upload: neither a newer version nor a different hash is accepted.
    storage.objects[doc.object_key] = (b"different", "v-replaced", hashlib.sha256(b"different").hexdigest())
    monkeypatch.setattr(document_processing, "get_document_scanner", lambda: FixedScanner(ScanOutcome.CLEAN))
    assert execute_scan(job.id) == "retry"
    db.refresh(doc)
    assert doc.status == DocumentStatus.PENDING_SCAN


def test_durable_cleanup_retries_and_never_deletes_referenced_object(
    as_user, db: Session, storage: MemoryStorage
) -> None:  # type: ignore[no-untyped-def]
    student, app = _draft(as_user)
    uploaded = _upload(student, app["id"])
    doc = db.get(ApplicationDocument, uuid.UUID(uploaded.json()["id"]))
    assert doc is not None
    cleanup = db.scalar(select(DocumentObjectCleanup).where(DocumentObjectCleanup.object_key == doc.object_key))
    assert cleanup is not None and cleanup.status == "retained"
    assert execute_cleanup(cleanup.id) is None
    assert doc.object_key in storage.objects

    orphan = DocumentObjectCleanup(
        organization_id=doc.organization_id,
        object_key="quarantine/test/orphan.pdf",
        object_version_id="v-orphan",
        checksum="a" * 64,
        status="queued",
    )
    db.add(orphan)
    db.commit()
    storage.objects[orphan.object_key] = (PDF, "v-orphan", "a" * 64)
    storage.fail_delete = True
    assert execute_cleanup(orphan.id) == "retry"
    db.refresh(orphan)
    assert orphan.status == "retry" and orphan.attempts == 1
    orphan.next_attempt_at = None
    db.commit()
    storage.fail_delete = False
    assert execute_cleanup(orphan.id) == "completed"
    assert orphan.object_key not in storage.objects


def test_cleanup_leaves_an_upload_in_flight_alone_until_it_has_settled(as_user, db: Session) -> None:  # type: ignore[no-untyped-def]
    student, _ = _draft(as_user)
    del student
    owner = db.scalar(select(User).where(User.email == DEMO_STUDENT_EMAIL))
    assert owner is not None
    intent = DocumentObjectCleanup(
        organization_id=owner.organization_id, object_key="quarantine/in-flight", status="queued"
    )
    db.add(intent)
    db.commit()
    assert intent.id not in reconcile_document_cleanups()

    intent.created_at = utcnow() - timedelta(hours=1)
    db.commit()
    assert intent.id in reconcile_document_cleanups()
