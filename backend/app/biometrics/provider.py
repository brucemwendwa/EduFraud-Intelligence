"""Vendor-neutral identity-verification provider interface.

EduShield never stores face images, document images or biometric templates. A provider
receives handles to captured samples, performs document, face, liveness and
presentation-attack checks on its side, and returns only scores and reason codes.
A production deployment would implement this protocol for an authorized commercial
identity-verification vendor under an institutional contract; this prototype ships
`SimulatedBiometricProvider`, which is clearly labelled as a simulation everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


class ConsentRequiredError(Exception):
    """The student has not consented to biometric verification; use an alternative method."""


@dataclass(frozen=True)
class VerificationRequest:
    # Opaque reference to the template held by the provider (never the template itself).
    biometric_reference_id: str
    # Handle to the captured probe. In the simulation this names a synthetic test sample.
    sample_handle: str
    student_ref: str
    trigger: str


@dataclass
class StageResult:
    stage: Literal["document", "face_match", "liveness", "presentation_attack"]
    outcome: Literal["pass", "fail", "inconclusive", "not_performed"]
    score: float | None
    reason_codes: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ProviderResult:
    provider: str
    mode: Literal["simulation", "live"]
    document_result: Literal["authentic", "suspicious", "unreadable"]
    document_type: str
    face_match_score: float | None
    liveness_score: float | None
    liveness_result: Literal["live", "not_live", "inconclusive"]
    pad_result: Literal["none_detected", "attack_detected", "inconclusive"]
    pad_attack_type: str | None
    quality_flags: list[str]
    stages: list[StageResult]


class IdentityVerificationProvider(Protocol):
    name: str
    mode: Literal["simulation", "live"]

    def verify(self, request: VerificationRequest) -> ProviderResult: ...
