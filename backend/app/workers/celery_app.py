"""Celery application. Used only when CELERY_BROKER_URL is set (e.g. Redis in docker compose)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.monitoring import init_error_monitoring

settings = get_settings()
init_error_monitoring(settings)

celery_app = Celery("edushield", broker=settings.celery_broker_url or "memory://", include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    # A queue outage must fail a dispatch quickly rather than hold a web request open.
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 5},
    redis_socket_connect_timeout=3,
    beat_schedule={
        "reconcile-document-scans": {"task": "document.reconcile", "schedule": 60.0},
        "reconcile-email": {"task": "email.reconcile", "schedule": 60.0},
        "purge-expired-credentials": {"task": "auth.purge_expired", "schedule": 3600.0},
    },
)
