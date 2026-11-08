"""Error monitoring and lightweight request metrics.

Sentry is optional and off unless SENTRY_DSN is set. Events are stripped before they leave the
process: no request bodies, cookies, headers, query strings, users or local variables.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import redact_text

log = logging.getLogger("edushield.monitoring")
_SAMPLE_SIZE = 2000


def scrub_event(event: dict[str, Any], _hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Keeps what is needed to find a bug and drops everything that could describe a person."""
    request = event.get("request") or {}
    event["request"] = {key: request[key] for key in ("method", "url") if key in request}
    if "url" in event["request"]:
        event["request"]["url"] = str(event["request"]["url"]).split("?", 1)[0]
    for key in ("user", "extra", "breadcrumbs", "server_name"):
        event.pop(key, None)
    for exception in (event.get("exception") or {}).get("values") or []:
        if exception.get("value"):
            exception["value"] = redact_text(str(exception["value"]))
        for frame in (exception.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    if event.get("message"):
        event["message"] = redact_text(str(event["message"]))
    return event


def init_error_monitoring(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        log.warning("sentry_sdk_not_installed")
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.env,
        release=settings.app_version,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub_event,
    )
    return True


@dataclass(frozen=True)
class RequestStats:
    sample_size: int
    p50_ms: float | None
    p95_ms: float | None
    server_error_rate: float | None


class RequestMetrics:
    """A rolling window of recent API requests in this process. Each instance reports only its own."""

    def __init__(self, size: int = _SAMPLE_SIZE) -> None:
        self._samples: deque[tuple[float, bool]] = deque(maxlen=size)
        self._lock = threading.Lock()

    def record(self, duration_ms: float, status_code: int) -> None:
        with self._lock:
            self._samples.append((duration_ms, status_code >= 500))

    def snapshot(self) -> RequestStats:
        with self._lock:
            samples = list(self._samples)
        if not samples:
            return RequestStats(0, None, None, None)
        durations = sorted(duration for duration, _ in samples)
        percentile = lambda share: round(durations[min(len(durations) - 1, int(len(durations) * share))], 1)  # noqa: E731
        return RequestStats(
            sample_size=len(samples),
            p50_ms=percentile(0.5),
            p95_ms=percentile(0.95),
            server_error_rate=round(sum(failed for _, failed in samples) / len(samples), 4),
        )

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()


request_metrics = RequestMetrics()
