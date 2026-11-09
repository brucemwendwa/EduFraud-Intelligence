from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks

from app.core.config import get_settings

logger = logging.getLogger("edushield.mail")


def dispatch_emails(outbox_ids: list[uuid.UUID], background: BackgroundTasks) -> None:
    """Hands committed outbox rows to delivery. A lost dispatch is picked up by the scheduler."""
    if get_settings().jobs_backend == "celery":
        from app.workers.tasks import deliver_email

        for outbox_id in outbox_ids:
            try:
                deliver_email.apply_async(args=[str(outbox_id)], retry=False)
            except Exception:  # noqa: BLE001 - the outbox row is durable
                logger.warning("email_dispatch_deferred", extra={"outbox_id": str(outbox_id)})
        return
    from app.services.email_outbox import deliver

    for outbox_id in outbox_ids:
        background.add_task(deliver, outbox_id)
