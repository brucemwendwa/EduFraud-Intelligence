"""Celery application. Used only when CELERY_BROKER_URL is set (e.g. Redis in docker compose)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery("edushield", broker=settings.celery_broker_url or "memory://", include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
)
