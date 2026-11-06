from __future__ import annotations

import uuid

from fastapi import BackgroundTasks

from app.core.config import get_settings


def enqueue_document_scan(job_id: uuid.UUID, background: BackgroundTasks) -> str:
    if get_settings().jobs_backend == "celery":
        from app.workers.tasks import run_document_scan

        run_document_scan.delay(str(job_id))
        return "celery"
    from app.services.document_processing import execute_scan

    background.add_task(execute_scan, job_id)
    return "inline"
