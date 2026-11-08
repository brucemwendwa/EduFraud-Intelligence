"""Fail-closed malware scanner boundary. No scanner ever defaults to clean."""

from __future__ import annotations

import hashlib
import logging
import socket
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.core.config import Settings, get_settings
from app.services.object_storage import get_object_storage

logger = logging.getLogger(__name__)
_CHUNK_BYTES = 64 * 1024


class ScanOutcome(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ScanResult:
    outcome: ScanOutcome
    provider: str


class DocumentScanner(Protocol):
    def scan(self, *, object_key: str, object_version_id: str | None, checksum: str, scan_token: str) -> ScanResult: ...


class UnavailableScanner:
    def scan(self, *, object_key: str, object_version_id: str | None, checksum: str, scan_token: str) -> ScanResult:
        del object_key, object_version_id, checksum, scan_token
        return ScanResult(ScanOutcome.UNAVAILABLE, "unconfigured")


def _read_reply(sock: socket.socket) -> bytes:
    reply = bytearray()
    while b"\0" not in reply:
        chunk = sock.recv(4096)
        if not chunk:
            break
        reply.extend(chunk)
    return bytes(reply).split(b"\0", 1)[0].strip()


@dataclass(frozen=True)
class ClamAVScanner:
    """Streams the exact stored object to a clamd daemon using its INSTREAM protocol."""

    host: str
    port: int
    timeout: int

    def _command(self, command: bytes) -> bytes | None:
        try:
            with socket.create_connection((self.host, self.port), timeout=min(self.timeout, 3)) as sock:
                sock.sendall(command)
                return _read_reply(sock)
        except OSError:
            return None

    def ping(self) -> bool:
        return self._command(b"zPING\0") == b"PONG"

    def signatures_published_at(self) -> datetime | None:
        """Publication time of the loaded virus definitions, from clamd's VERSION reply."""
        reply = self._command(b"zVERSION\0") or b""
        parts = reply.decode("ascii", "ignore").split("/")
        if len(parts) < 3:
            return None
        try:
            return datetime.strptime(" ".join(parts[2].split()), "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
        except ValueError:
            return None

    def _instream(self, body: bytes) -> bytes:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(b"zINSTREAM\0")
            for start in range(0, len(body), _CHUNK_BYTES):
                chunk = body[start : start + _CHUNK_BYTES]
                sock.sendall(struct.pack("!I", len(chunk)) + chunk)
            sock.sendall(struct.pack("!I", 0))
            return _read_reply(sock)

    def scan(self, *, object_key: str, object_version_id: str | None, checksum: str, scan_token: str) -> ScanResult:
        del scan_token
        body = get_object_storage().get(key=object_key, version_id=object_version_id)
        if hashlib.sha256(body).hexdigest() != checksum:
            return ScanResult(ScanOutcome.ERROR, "clamav")
        reply = self._instream(body)
        # Only clamd's exact success reply clears a document; anything else is treated as a failed scan.
        if reply == b"stream: OK":
            return ScanResult(ScanOutcome.CLEAN, "clamav")
        if reply.startswith(b"stream: ") and reply.endswith(b" FOUND"):
            return ScanResult(ScanOutcome.INFECTED, "clamav")
        logger.warning("clamav_scan_error")
        return ScanResult(ScanOutcome.ERROR, "clamav")


def get_clamav_scanner(settings: Settings | None = None) -> ClamAVScanner | None:
    settings = settings or get_settings()
    if settings.document_scanner_provider != "clamav" or not settings.clamav_host:
        return None
    return ClamAVScanner(settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)


def get_document_scanner() -> DocumentScanner:
    # Without a real scanner, every document stays quarantined. A clean result is never simulated.
    return get_clamav_scanner() or UnavailableScanner()
