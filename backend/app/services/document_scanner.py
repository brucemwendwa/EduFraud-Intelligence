"""Fail-closed malware scanner boundary. No scanner ever defaults to clean."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.core.config import get_settings


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


def get_document_scanner() -> DocumentScanner:
    # A production adapter is deliberately not guessed or simulated.
    if get_settings().document_scanner_provider == "unconfigured":
        return UnavailableScanner()
    return UnavailableScanner()
