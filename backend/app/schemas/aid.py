"""Schemas for students, applications, enrollment, disbursements and related-record links."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.models.enums import ApplicationStatus, ReviewStatus
from app.schemas.common import OrgRef, ReasonText, Schema


class StudentRef(Schema):
    id: uuid.UUID
    student_ref: str
    masked_name: str


class IdentityTokenOut(Schema):
    token_type: str
    handle: str
    shared_in_scope: int = Field(description="Other student records in your scope with the same token")
    shared_other_institutions: int = Field(description="Matches at other institutions (count only; details hidden)")


class StudentDetail(StudentRef):
    birth_year: int
    state_of_residence: str
    biometric_consent: bool
    biometric_consent_at: datetime | None
    identity_tokens: list[IdentityTokenOut]


class RevealRequest(Schema):
    reason: ReasonText


class RevealResponse(Schema):
    student_id: uuid.UUID
    first_name: str
    last_name: str
    revealed_at: datetime
    notice: str = "This access has been recorded in the audit trail."


class EnrollmentOut(Schema):
    id: uuid.UUID
    organization_id: uuid.UUID
    term: str
    term_start: date
    program: str
    credit_hours: int
    modality: str
    status: str
    last_attendance_at: datetime | None


class DestinationOut(Schema):
    id: uuid.UUID
    handle: str
    destination_type: str
    display_suffix: str


class DisbursementRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    application_id: uuid.UUID | None
    application_ref: str | None
    fund_type: str
    amount: Decimal
    disbursed_at: datetime
    status: str
    destination: DestinationOut
    destination_changed_at: datetime | None
    risk_score: float | None
    risk_flags: list[str]
    hold_reason: str | None
    held_at: datetime | None


class DestinationUsage(Schema):
    students_in_scope: int
    students_other_institutions: int
    first_seen_at: datetime


class DisbursementDetail(DisbursementRow):
    destination_usage: DestinationUsage
    same_destination: list[DisbursementRow]
    student_disbursements: list[DisbursementRow]


class DisbursementSummary(Schema):
    total_count: int
    total_amount: Decimal
    flagged_count: int
    flagged_amount: Decimal
    held_count: int
    held_amount: Decimal
    scheduled_count: int


class HoldRequest(Schema):
    reason: ReasonText


class VerificationRow(Schema):
    id: uuid.UUID
    reference: str
    trigger: str
    method: str
    provider: str
    provider_mode: str
    status: str
    face_match_score: float | None
    liveness_result: str
    pad_result: str
    pad_attack_type: str | None
    completed_at: datetime | None
    created_at: datetime


class ApplicationRow(Schema):
    id: uuid.UUID
    reference: str
    organization: OrgRef
    student: StudentRef
    submitted_at: datetime
    award_year: str
    status: str
    requested_amount: Decimal
    verification_status: str
    review_status: str
    risk_score: float | None
    risk_level: str | None
    last_assessed_at: datetime | None
    scenario_key: str | None
    open_alerts: int = 0


class RelatedApplication(Schema):
    id: uuid.UUID
    reference: str
    student_ref: str
    organization_name: str
    risk_level: str | None
    risk_score: float | None


class RelatedGroup(Schema):
    kind: str
    label: str
    handle: str
    matches: list[RelatedApplication]
    other_institution_matches: int


class ApplicationRecord(ApplicationRow):
    dependency_status: str
    enrollment_intensity: str
    program: str
    student_aid_index: int
    submission_channel: str
    device_handle: str | None
    ip_handle: str | None
    student_detail: StudentDetail
    enrollments: list[EnrollmentOut]
    disbursements: list[DisbursementRow]
    verifications: list[VerificationRow]
    related: list[RelatedGroup]


class ReviewUpdate(Schema):
    """A human review decision. The platform never changes status on its own."""

    review_status: Literal[ReviewStatus.IN_REVIEW, ReviewStatus.CLEARED, ReviewStatus.ESCALATED]
    application_status: (
        Literal[ApplicationStatus.IN_REVIEW, ApplicationStatus.ON_HOLD, ApplicationStatus.APPROVED] | None
    ) = None
    note: str = Field(min_length=5, max_length=1000)
