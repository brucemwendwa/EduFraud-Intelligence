"""Job dispatch: Celery when a broker is configured, otherwise in-process after the response is sent."""

from __future__ import annotations

import uuid

from fastapi import BackgroundTasks

from app.core.config import get_settings


def enqueue_detection_run(run_id: uuid.UUID, background: BackgroundTasks) -> str:
    if get_settings().jobs_backend == "celery":
        from app.workers.tasks import run_detection

        run_detection.delay(str(run_id))
        return "celery"
    from app.services.detection_runs import execute_run

    background.add_task(execute_run, run_id)
    return "inline"
