"""Proves the scheduler, Redis and a worker are all connected.

Beat dispatches this task and a worker runs it, so a recent tick means the whole path is working.
"""

from __future__ import annotations

import time

from app.core.ratelimit import shared_store

_KEY = "edushield:scheduler:last_tick"
_RETENTION_SECONDS = 3600


def record_tick() -> None:
    store = shared_store()
    if store is not None:
        store.set(_KEY, int(time.time()), ex=_RETENTION_SECONDS)


def seconds_since_last_tick() -> int | None:
    """None when no tick is on record. Raises if Redis cannot be read."""
    store = shared_store()
    if store is None:
        return None
    value = store.get(_KEY)
    return max(0, int(time.time()) - int(value)) if value is not None else None
