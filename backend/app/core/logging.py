"""Structured JSON logging with defensive redaction of sensitive values.

Request bodies are never logged. As a second line of defence, every record passes
through `RedactingFilter`, which masks sensitive keys in structured `extra` data and
scrubs SSN-, JWT- and bearer-token-shaped strings from messages.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|authorization|cookie|ssn|social|account_?number|routing|"
    r"date_of_birth|dob|biometric_template|face_image",
    re.IGNORECASE,
)
_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-shaped
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\beyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]+"),  # JWT-shaped
]

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def redact_text(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_value(key: str, value: Any) -> Any:
    if SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(key, v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - malformed format args must not break logging
            message = str(record.msg)
        record.msg = redact_text(message)
        record.args = None
        for key in list(record.__dict__):
            if key not in _STANDARD_ATTRS:
                record.__dict__[key] = redact_value(key, record.__dict__[key])
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorn's access log includes raw query strings; our request middleware logs a safe version instead.
    logging.getLogger("uvicorn.access").disabled = True
