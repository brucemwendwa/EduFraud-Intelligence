from __future__ import annotations

import uuid

from app.services.detection_runs import execute_run
from app.workers.celery_app import celery_app


@celery_app.task(name="detection.run")
def run_detection(run_id: str) -> None:
    execute_run(uuid.UUID(run_id))
