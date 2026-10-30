"""SIMULATED biometric provider for demonstrations. It performs no real biometric processing.

Each synthetic "test sample" describes what a capture would contain (the enrolled student,
an impostor, a printed photo, a replayed video, a damaged document…). Scores are derived
deterministically from the sample and the student reference, so demonstrations and tests
are repeatable. No camera, image or biometric template is ever used or stored.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from app.biometrics.provider import ProviderResult, StageResult, VerificationRequest


@dataclass(frozen=True)
class TestSample:
    key: str
    label: str
    description: str
    expected: str
    document: str  # authentic | suspicious | unreadable
    face: tuple[float, float]
    liveness: tuple[float, float]
    attack: str | None = None


TEST_SAMPLES: dict[str, TestSample] = {
    s.key: s
    for s in (
        TestSample(
            "enrolled_student",
            "Enrolled student",
            "The account owner presents their own ID and completes a live selfie.",
            "Pass",
            "authentic",
            (0.92, 0.98),
            (0.91, 0.99),
        ),
        TestSample(
            "different_person",
            "Different person (impostor)",
            "Someone else completes the selfie using the student's stolen ID details.",
            "Fail: face mismatch",
            "authentic",
            (0.12, 0.30),
            (0.88, 0.97),
        ),
        TestSample(
            "impostor_screen_replay",
            "Impostor replaying a video",
            "A video of another face is replayed on a phone screen held to the camera.",
            "Fail: mismatch and presentation attack",
            "authentic",
            (0.18, 0.26),
            (0.10, 0.22),
            "screen_replay",
        ),
        TestSample(
            "printed_photo",
            "Printed photo of the student",
            "A printed photograph of the real student is held up to the camera.",
            "Fail: presentation attack",
            "authentic",
            (0.80, 0.88),
            (0.08, 0.20),
            "printed_photo",
        ),
        TestSample(
            "altered_document",
            "Altered identity document",
            "The ID's photo and data fields show signs of tampering.",
            "Fail: suspicious document",
            "suspicious",
            (0.55, 0.70),
            (0.85, 0.95),
        ),
        TestSample(
            "unreadable_document",
            "Unreadable document (glare)",
            "Heavy glare makes the document unreadable; the student should retry.",
            "Inconclusive: manual review",
            "unreadable",
            (0.86, 0.94),
            (0.80, 0.92),
        ),
    )
}

FACE_MATCH_THRESHOLD = 0.80
FACE_MISMATCH_THRESHOLD = 0.50
LIVENESS_THRESHOLD = 0.70


class SimulatedBiometricProvider:
    name = "edushield-simulated-idv"
    mode = "simulation"

    def verify(self, request: VerificationRequest) -> ProviderResult:
        sample = TEST_SAMPLES.get(request.sample_handle)
        if sample is None:
            raise ValueError(f"Unknown synthetic test sample: {request.sample_handle}")
        seed = int(hashlib.sha256(f"{sample.key}:{request.student_ref}".encode()).hexdigest()[:12], 16)
        rng = random.Random(seed)
        face = round(rng.uniform(*sample.face), 3)
        liveness = round(rng.uniform(*sample.liveness), 3)

        doc_outcome = {"authentic": "pass", "suspicious": "fail", "unreadable": "inconclusive"}[sample.document]
        doc_codes = {
            "authentic": [],
            "suspicious": ["DOC_TAMPER_INDICATORS"],
            "unreadable": ["DOC_GLARE", "DOC_MRZ_UNREADABLE"],
        }
        live = liveness >= LIVENESS_THRESHOLD
        face_outcome = (
            "pass" if face >= FACE_MATCH_THRESHOLD else "fail" if face < FACE_MISMATCH_THRESHOLD else "inconclusive"
        )
        stages = [
            StageResult(
                "document",
                doc_outcome,
                None,
                doc_codes[sample.document],  # type: ignore[arg-type]
                "Driver's license security features and data consistency",
            ),
            StageResult(
                "face_match",
                face_outcome,
                face,  # type: ignore[arg-type]
                [] if face_outcome == "pass" else ["FACE_SIMILARITY_LOW"],
                f"Similarity to the enrolled reference: {face:.2f} (match ≥ {FACE_MATCH_THRESHOLD:.2f})",
            ),
            StageResult(
                "liveness",
                "pass" if live else "fail",
                liveness,
                [] if live else ["LIVENESS_FAILED"],
                f"Liveness confidence {liveness:.2f} (live ≥ {LIVENESS_THRESHOLD:.2f})",
            ),
            StageResult(
                "presentation_attack",
                "fail" if sample.attack else "pass",
                None,
                [f"PAD_{sample.attack.upper()}"] if sample.attack else [],
                f"Detected: {sample.attack.replace('_', ' ')}" if sample.attack else "No spoofing artefacts detected",
            ),
        ]
        return ProviderResult(
            provider=self.name,
            mode="simulation",
            document_result=sample.document,  # type: ignore[arg-type]
            document_type="drivers_license",
            face_match_score=face,
            liveness_score=liveness,
            liveness_result="live" if live else "not_live",
            pad_result="attack_detected" if sample.attack else "none_detected",
            pad_attack_type=sample.attack,
            quality_flags=["glare"] if sample.document == "unreadable" else [],
            stages=stages,
        )


def get_provider() -> SimulatedBiometricProvider:
    """Single place to swap in a licensed vendor implementation of IdentityVerificationProvider."""
    return SimulatedBiometricProvider()
