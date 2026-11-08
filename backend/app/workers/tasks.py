from __future__ import annotations

import uuid

from app.services.account_maintenance import purge_expired_credentials
from app.services.detection_runs import execute_run
from app.services.document_processing import (
    execute_cleanup,
    execute_scan,
    reconcile_document_cleanups,
    reconcile_document_scans,
)
from app.services.email_outbox import deliver, due_messages
from app.workers.celery_app import celery_app


@celery_app.task(name="detection.run")
def run_detection(run_id: str) -> None:
    execute_run(uuid.UUID(run_id))


@celery_app.task(name="document.scan")
def run_document_scan(job_id: str) -> None:
    execute_scan(uuid.UUID(job_id))


@celery_app.task(name="document.reconcile")
def reconcile_document_scan_jobs() -> None:
    for job_id in reconcile_document_scans():
        run_document_scan.delay(str(job_id))
    for cleanup_id in reconcile_document_cleanups():
        run_document_cleanup.delay(str(cleanup_id))


@celery_app.task(name="document.cleanup")
def run_document_cleanup(cleanup_id: str) -> None:
    execute_cleanup(uuid.UUID(cleanup_id))


@celery_app.task(name="email.deliver")
def deliver_email(outbox_id: str) -> None:
    deliver(uuid.UUID(outbox_id))


@celery_app.task(name="email.reconcile")
def reconcile_email() -> None:
    for outbox_id in due_messages():
        deliver_email.delay(str(outbox_id))


@celery_app.task(name="auth.purge_expired")
def purge_expired() -> None:
    purge_expired_credentials()
