"""Abuse limits for unauthenticated endpoints.

Counters live in Redis when one is configured, so the limit holds across every API instance. If
Redis is unavailable each process enforces the limit on its own: weaker, but never unlimited.
Account lockout (stored on the user row) remains the primary brute-force control.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache

import redis

from app.core.config import get_settings

logger = logging.getLogger("edushield.ratelimit")


@lru_cache
def _client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)


def shared_store() -> redis.Redis | None:
    url = get_settings().rate_limit_store_url
    return _client(url) if url else None


class RateLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        store = shared_store()
        if store is not None:
            try:
                return self._allow_shared(store, key)
            except redis.RedisError:
                logger.warning("rate_limit_store_unavailable", extra={"limiter": self.name})
        return self._allow_local(key)

    def _allow_shared(self, store: redis.Redis, key: str) -> bool:
        window = int(time.time() // self.window)
        digest = hashlib.sha256(key.encode()).hexdigest()[:32]  # client addresses are not stored in Redis
        counter = f"edushield:ratelimit:{self.name}:{digest}:{window}"
        pipeline = store.pipeline()
        pipeline.incr(counter)
        pipeline.expire(counter, int(self.window) + 1)
        count, _ = pipeline.execute()
        return int(count) <= self.limit

    def _allow_local(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = RateLimiter("login", limit=20, window_seconds=60)
activation_limiter = RateLimiter("activation", limit=10, window_seconds=60)
password_reset_limiter = RateLimiter("password_reset", limit=10, window_seconds=60)
