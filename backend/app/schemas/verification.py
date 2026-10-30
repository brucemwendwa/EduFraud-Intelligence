from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.enums import VerificationTrigger
from app.schemas.aid import StudentRef
from app.schemas.common import OrgRef, Schema


class TestSampleOut(Schema):
    key: str
    label: str
    description: str
    expected: str


class ProviderInfo(Schema):
    name: str
    mode: str
    disclaimer: str
    data_handling: list[str]
    thresholds: dict[str, float]
    samples: list[TestSampleOut]
    triggers: list[str]
    alternative_methods: list[str]


class StageOut(Schema):
    stage: str
    outcome: str
    score: float | None
    reason_codes: list[str]
    detail: str


class VerificationOut(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    application_id: uuid.UUID | None
    application_ref: str | None
    trigger: str
    method: str
    provider: str
    provider_mode: str
    status: str
    document_result: str
    face_match_score: float | None
    liveness_score: float | None
    liveness_result: str
    pad_result: str
    pad_attack_type: str | None
    risk_indicators: list[str]
    recommended_action: str
    sample_key: str | None
    stages: list[StageOut]
    notes: str | None
    initiated_by: str | None
    completed_at: datetime | None
    created_at: datetime
    resulting_risk_score: float | None = None
    resulting_risk_level: str | None = None


class BiometricVerificationIn(Schema):
    application_id: uuid.UUID
    trigger: VerificationTrigger
    sample_key: str = Field(max_length=48)


class AlternativeVerificationIn(Schema):
    application_id: uuid.UUID
    trigger: VerificationTrigger
    method: Literal["in_person_id_check", "officer_video_call", "mailed_code"]
    outcome: Literal["passed", "failed"]
    notes: str = Field(min_length=10, max_length=1000)


class VerificationStats(Schema):
    total: int
    passed: int
    failed: int
    review: int
    pass_rate: float | None
    attacks_detected: int
    biometric_share: float | None
    by_trigger: dict[str, int]
    by_method: dict[str, int]
    daily: list[dict[str, Any]]
