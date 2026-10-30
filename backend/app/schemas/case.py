"""Request and response schemas for the human-led investigation workspace."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.enums import CaseResolution
from app.schemas.common import Schema, UserRef

Priority = Literal["low", "medium", "high", "urgent"]


class CaseCreate(Schema):
    """Open a case from an alert and/or application. Title, category and priority default from the evidence."""

    title: str | None = Field(default=None, min_length=5, max_length=200)
    application_id: uuid.UUID | None = None
    alert_id: uuid.UUID | None = None
    fraud_category: str | None = Field(default=None, min_length=2, max_length=32)
    priority: Priority | None = None
    assigned_to_id: uuid.UUID | None = None
    due_at: datetime | None = None


class CaseUpdate(Schema):
    """Edit case details. Status may only move new → under_review here; other changes need a decision."""

    title: str | None = Field(default=None, min_length=5, max_length=200)
    priority: Priority | None = None
    status: Literal["under_review"] | None = None
    due_at: datetime | None = None


class CaseAssign(Schema):
    assigned_to_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class CaseResolve(Schema):
    """Legacy resolve payload (kept for compatibility); prefer POST /cases/{id}/decision."""

    resolution: CaseResolution
    summary: str = Field(min_length=20, max_length=5000)


class CaseDecisionIn(Schema):
    decision: Literal["escalate", "resolve", "reopen", "close"]
    outcome: CaseResolution | None = Field(
        default=None,
        description="Required for resolve: confirmed_fraud, no_fraud_found, insufficient_evidence, referred_externally",
    )
    justification: str = Field(min_length=20, max_length=5000)
    acknowledged: bool = Field(
        description=(
            "The investigator confirms they reviewed the evidence and that this is their own decision, not the AI's"
        )
    )


class CaseNoteCreate(Schema):
    body: str = Field(min_length=2, max_length=5000)


class CaseEvidenceCreate(Schema):
    """Reference a record (snapshotted server-side) or describe evidence in free text (document_note)."""

    evidence_type: str = Field(
        pattern="^(alert|risk_assessment|verification|disbursement|application|network_cluster|document_note)$"
    )
    ref_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=2, max_length=200)
    summary: str | None = Field(default=None, min_length=2, max_length=5000)
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


class CaseDecisionOut(Schema):
    id: uuid.UUID
    decision: str
    outcome: str | None
    finding: str
    from_status: str
    to_status: str
    justification: str
    decided_by: UserRef | None
    decided_at: datetime


class TimelineEntryOut(Schema):
    at: datetime
    kind: str
    title: str
    actor: str | None
    detail: str | None


class CaseApplicationRef(Schema):
    id: uuid.UUID
    reference: str
    status: str
    review_status: str
    risk_score: float | None
    risk_level: str | None
    student_ref: str
    masked_name: str


class CaseAlertRef(Schema):
    id: uuid.UUID
    reference: str
    title: str
    severity: str
    status: str


class CaseRow(Schema):
    id: uuid.UUID
    reference: str
    title: str
    application_id: uuid.UUID | None
    application_ref: str | None
    fraud_category: str
    priority: str
    status: str
    finding: str
    risk_score_at_open: float | None
    assigned_to: UserRef | None
    created_by: UserRef | None
    due_at: datetime | None
    overdue: bool
    created_at: datetime
    updated_at: datetime


class CaseDetail(CaseRow):
    resolution: str | None
    resolution_summary: str | None
    resolved_at: datetime | None
    closed_at: datetime | None
    application: CaseApplicationRef | None
    alerts: list[CaseAlertRef]
    evidence: list[CaseEvidenceOut]
    notes: list[CaseNoteOut]
    decisions: list[CaseDecisionOut]
    timeline: list[TimelineEntryOut]


class CaseSummary(Schema):
    open: int
    unassigned: int
    escalated: int
    overdue: int
    resolved: int
    by_finding: dict[str, int]


class AssigneeOut(Schema):
    id: uuid.UUID
    full_name: str
    email: str
    title: str | None
    open_cases: int
