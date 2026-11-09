"""Schemas for student ID-linked accounts, cards, transactions, devices, security events and verification requests.

Identifiers are always tokenized or masked: provider accounts and devices appear as short
handles, cards only by their last four characters. Locations are city/country only and are
returned solely to users holding `location:read`; others see `location_restricted: true`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from app.models.enums import VerificationRequestMethod, VerificationRequestTrigger
from app.schemas.aid import DestinationOut, DisbursementRow, StudentRef, VerificationRow
from app.schemas.common import OrgRef, ReasonText, Schema, UserRef
from app.schemas.risk import AlertRow, AssessmentHistoryItem, RiskAssessmentOut


class IndicatorOut(Schema):
    code: str
    title: str
    category: str
    points: float
    description: str | None = None


class CardSummary(Schema):
    id: uuid.UUID
    reference: str
    masked_number: str = Field(description="Last four characters only, e.g. '•••• 0412'")
    status: str


class CardOut(CardSummary):
    organization: OrgRef
    student: StudentRef
    account_id: uuid.UUID | None
    account_ref: str | None
    issued_at: datetime
    activated_at: datetime | None
    expires_on: Any
    reported_lost_at: datetime | None
    report_channel: str | None
    blocked_at: datetime | None
    block_confirmation: str | None
    replacement_requested_at: datetime | None
    replaced_by_id: uuid.UUID | None
    replaced_by_ref: str | None
    verified_since_report: bool = Field(description="Identity re-verified after the loss report (replacement allowed)")


class AccountRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    department: str | None
    status: str
    sensitive_actions_restricted: bool
    study_mode: str
    provider_mode: str
    card: CardSummary | None
    allocated_total: Decimal
    available_balance: Decimal | None
    balance_as_of: datetime | None
    last_transaction_at: datetime | None
    verification_status: str
    risk_score: float | None
    risk_level: str | None
    scenario_key: str | None


class DeviceOut(Schema):
    id: uuid.UUID
    handle: str
    label: str
    platform: str
    trust_status: str
    trust_reason: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_shared_kiosk: bool
    student: StudentRef
    other_accounts_in_scope: int
    other_accounts_other_institutions: int


class SecurityEventRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    account_id: uuid.UUID | None
    account_ref: str | None
    card_ref: str | None
    event_type: str
    source: str
    outcome: str
    decision: str | None
    occurred_at: datetime
    device: DeviceOut | None
    location: str | None
    location_restricted: bool
    destination: DestinationOut | None
    risk_score: float | None
    risk_level: str | None
    indicators: list[IndicatorOut]
    note: str | None
    scenario_key: str | None


class TransactionRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    account_id: uuid.UUID
    account_ref: str
    card_ref: str | None
    transaction_type: str
    channel: str
    merchant_name: str
    merchant_category: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    location: str | None
    location_restricted: bool
    destination: DestinationOut | None
    status: str
    decline_reason: str | None
    risk_score: float | None
    risk_level: str | None
    indicators: list[IndicatorOut]
    review_status: str
    scenario_key: str | None


class TransactionDetail(TransactionRow):
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    account_status: str
    account_restricted: bool
    recent_transactions: list[TransactionRow]
    related_events: list[SecurityEventRow]
    alerts: list[AlertRow]


class VerificationEventOut(Schema):
    step: str
    status_after: str
    actor_label: str
    note: str | None
    details: dict[str, Any]
    created_at: datetime


class VerificationRequestRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    account_id: uuid.UUID | None
    account_ref: str | None
    card_ref: str | None
    alert_id: uuid.UUID | None
    alert_ref: str | None
    case_id: uuid.UUID | None
    case_ref: str | None
    trigger: str
    reason: str
    pathway: str
    method: str | None
    status: str
    assigned_to: UserRef | None
    notified_at: datetime | None
    due_at: datetime | None
    appointment_at: datetime | None
    location_note: str | None
    decided_at: datetime | None
    access_restored: bool
    created_at: datetime
    updated_at: datetime


class MethodOption(Schema):
    method: str
    label: str
    pathway: str
    available: bool
    reason: str | None


class VerificationRequestDetail(VerificationRequestRow):
    outcome_reason: str | None
    decided_by: str | None
    biometric_consent: bool
    study_mode: str | None
    embassy_arrangement: str | None
    methods: list[MethodOption]
    identity_verification_ref: str | None
    events: list[VerificationEventOut]


class AccountDetail(AccountRow):
    provider_key: str
    provider_account_handle: str
    status_reason: str | None
    restriction_reason: str | None
    restricted_at: datetime | None
    registered_location: str | None
    location_restricted: bool
    opened_at: datetime
    currency: str
    cards: list[CardOut]
    devices: list[DeviceOut]
    allocations: list[DisbursementRow]
    transactions: list[TransactionRow]
    security_events: list[SecurityEventRow]
    assessment: RiskAssessmentOut | None
    assessment_history: list[AssessmentHistoryItem]
    verification_requests: list[VerificationRequestRow]
    verification_attempts: list[VerificationRow]
    alerts: list[AlertRow]
    cases: list[dict[str, Any]]


class AccountSummary(Schema):
    total: int
    by_status: dict[str, int]
    restricted: int
    by_risk: dict[str, int]
    allocated_total: Decimal
    cards_by_status: dict[str, int]
    verification_open: int


class TransactionSummary(Schema):
    total: int
    flagged: int
    declined: int
    unreviewed_flagged: int
    by_indicator: dict[str, int]
    by_category: dict[str, int]
    amount_total: Decimal


class SecuritySummary(Schema):
    window_days: int
    events: int
    by_type: dict[str, int]
    new_devices: int
    failed_logins: int
    password_resets: int
    shared_devices: int
    elevated_events: int


class VerificationRequestSummary(Schema):
    by_status: dict[str, int]
    by_pathway: dict[str, int]
    open: int
    overdue: int


# ---------------------------------------------------------------- requests


class ReasonIn(Schema):
    reason: ReasonText


class ReportLostIn(Schema):
    channel: Literal["student_portal", "phone", "in_person", "officer"] = "officer"
    note: str | None = Field(default=None, max_length=500)
    block: bool = Field(default=True, description="Ask the provider to block the card immediately")


class CardNoteIn(Schema):
    note: str = Field(min_length=5, max_length=500)


class LinkCardIn(Schema):
    account_id: uuid.UUID


class TransactionReviewIn(Schema):
    decision: Literal["cleared", "suspicious"]
    note: ReasonText


class DeviceTrustIn(Schema):
    trust_status: Literal["trusted", "suspicious"]
    reason: ReasonText


class VerificationRequestCreate(Schema):
    account_id: uuid.UUID
    trigger: VerificationRequestTrigger = VerificationRequestTrigger.OFFICER_REQUEST
    reason: ReasonText
    alert_id: uuid.UUID | None = None
    case_id: uuid.UUID | None = None


class VerificationScheduleIn(Schema):
    appointment_at: datetime
    location_note: str | None = Field(default=None, max_length=160)


class VerificationStartIn(Schema):
    method: VerificationRequestMethod
    note: str | None = Field(default=None, max_length=500)


class VerificationCheckIn(Schema):
    step: Literal[
        "documents_checked",
        "identity_procedure_completed",
        "video_session_completed",
        "alternative_method_completed",
        "embassy_confirmation_received",
    ]
    result: Literal["pass", "fail", "inconclusive"]
    note: str = Field(min_length=5, max_length=500)


class VerificationLivenessIn(Schema):
    sample_key: str = Field(min_length=3, max_length=48)


class VerificationDecisionIn(Schema):
    outcome: Literal["verified", "failed", "escalated", "additional_info_required"]
    reason: str = Field(min_length=10, max_length=1000)
    restore_access: bool = True
