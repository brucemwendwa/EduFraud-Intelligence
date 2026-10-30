"""Request and response schemas for the human-led investigation workspace."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import Schema, UserRef


class CaseCreate(Schema):
    title: str = Field(min_length=5, max_length=200)
    application_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    fraud_category: str = Field(min_length=2, max_length=32)
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")
    assigned_to_id: uuid.UUID | None = None
    due_at: datetime | None = None


class CaseUpdate(Schema):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    priority: str | None = Field(default=None, pattern="^(low|medium|high|urgent)$")
    status: str | None = Field(default=None, pattern="^(new|under_review|escalated)$")
    due_at: datetime | None = None


class CaseAssign(Schema):
    assigned_to_id: uuid.UUID | None = None


class CaseResolve(Schema):
    resolution: str = Field(pattern="^(confirmed_fraud|no_fraud_found|insufficient_evidence|referred_externally)$")
    summary: str = Field(min_length=10, max_length=5000)


class CaseNoteCreate(Schema):
    body: str = Field(min_length=2, max_length=5000)


class CaseEvidenceCreate(Schema):
    evidence_type: str = Field(
        pattern="^(alert|risk_assessment|verification|disbursement|application|network_cluster|document_note)$"
    )
    title: str = Field(min_length=2, max_length=200)
    summary: str = Field(min_length=2, max_length=5000)
    ref_id: uuid.UUID | None = None
    ref_label: str | None = Field(default=None, max_length=48)
    data: dict[str, Any] = Field(default_factory=dict)


class CaseNoteOut(Schema):
    id: uuid.UUID
    body: str
    created_at: datetime
    author: UserRef | None


class CaseEvidenceOut(Schema):
    id: uuid.UUID
    evidence_type: str
    ref_id: uuid.UUID | None
    ref_label: str | None
    title: str
    summary: str
    data: dict[str, Any]
    created_at: datetime
    added_by: UserRef | None


class CaseRow(Schema):
    id: uuid.UUID
    reference: str
    title: str
    application_id: uuid.UUID | None
    fraud_category: str
    priority: str
    status: str
    risk_score_at_open: float | None
    assigned_to: UserRef | None
    created_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class CaseDetail(CaseRow):
    resolution: str | None
    resolution_summary: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    due_at: datetime | None
    evidence: list[CaseEvidenceOut]
    notes: list[CaseNoteOut]
