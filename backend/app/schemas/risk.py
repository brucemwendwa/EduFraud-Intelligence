"""Schemas for explainable risk assessments, alerts and the detection engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.aid import ApplicationRecord, StudentRef
from app.schemas.common import OrgRef, Schema


class FraudSignalOut(Schema):
    code: str
    category: str
    severity: str
    weight: float = Field(description="Strength of this evidence on its own (0-1)")
    points: float = Field(description="This signal's share of the final score; points sum to the score")
    title: str
    description: str
    evidence: dict[str, Any]
    method: str
    version: str


class RiskAssessmentOut(Schema):
    id: uuid.UUID
    score: float
    level: str
    method: str
    rules_version: str
    model_version: str | None
    explanation: str
    recommended_action: str
    triggered_by: str
    created_at: datetime
    signals: list[FraudSignalOut]


class AssessmentHistoryItem(Schema):
    id: uuid.UUID
    score: float
    level: str
    triggered_by: str
    created_at: datetime


class AlertRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    category: str
    severity: str
    title: str
    summary: str
    status: str
    risk_score: float | None
    application_id: uuid.UUID | None
    application_ref: str | None
    case_id: uuid.UUID | None
    case_ref: str | None
    created_at: datetime
    updated_at: datetime


class AlertDetail(AlertRow):
    student: StudentRef | None
    assessment: RiskAssessmentOut | None
    disbursement_id: uuid.UUID | None
    disbursement_ref: str | None
    verification_id: uuid.UUID | None
    verification_ref: str | None
    triage_note: str | None
    triaged_by: str | None
    triaged_at: datetime | None


class AlertTriage(Schema):
    action: Literal["acknowledge", "dismiss", "reopen"]
    note: str | None = Field(default=None, max_length=500)


class AlertSummary(Schema):
    open: int
    acknowledged: int
    in_investigation: int
    critical_open: int
    by_category: dict[str, int]


class DetectionRunOut(Schema):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    status: str
    mode: str
    rules_version: str
    model_version: str | None
    applications_scored: int
    disbursements_scored: int
    alerts_created: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RuleOut(Schema):
    code: str
    category: str
    method: str
    max_weight: float
    description: str


class ModelCardOut(Schema):
    version: str
    algorithm: str
    trained_on: str
    features: list[str]
    excluded_features: list[str]
    explanation_method: str
    max_weight: float
    evaluation: str


class DetectionStatus(Schema):
    method: str
    rules_version: str
    model_version: str
    graph_version: str
    jobs_backend: str
    last_run: DetectionRunOut | None
    recent_runs: list[DetectionRunOut]
    assessed_applications: int
    model_card: ModelCardOut
    rules: list[RuleOut]
    level_thresholds: dict[str, float]
    principles: list[str]


class ScenarioCheck(Schema):
    scenario: str
    label: str
    kind: Literal["fraud", "control"]
    applications: int
    expected: str
    expected_signals: list[str]
    observed_levels: dict[str, int]
    observed_signals: list[str]
    passed: bool


class ApplicationDetail(ApplicationRecord):
    """Application workspace: the record plus its explainable assessment, history and alerts."""

    assessment: RiskAssessmentOut | None
    assessment_history: list[AssessmentHistoryItem]
    alerts: list[AlertRow]
