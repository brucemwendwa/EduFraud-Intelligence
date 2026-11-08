from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks

from app.core.config import get_settings

logger = logging.getLogger("edushield.documents")


def enqueue_document_scan(job_id: uuid.UUID, background: BackgroundTasks) -> str:
    if get_settings().jobs_backend == "celery":
        from app.workers.tasks import run_document_scan

        try:
            run_document_scan.apply_async(args=[str(job_id)], retry=False)
        except Exception:  # noqa: BLE001 - the job row is durable and the scheduler dispatches it when the queue recovers
            logger.warning("document_scan_dispatch_deferred", extra={"job_id": str(job_id)})
            return "deferred"
        return "celery"
    from app.services.document_processing import execute_scan

    background.add_task(execute_scan, job_id)
    return "inline"
