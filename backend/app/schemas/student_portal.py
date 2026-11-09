from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.schemas.common import Schema


class StudentPortalApplication(Schema):
    id: uuid.UUID
    reference: str
    status: str
    award_year: str | None
    program: str | None
    requested_amount: Decimal | None
    submitted_at: datetime | None
    is_editable: bool


class StudentPortalOut(Schema):
    student_ref: str
    applications: list[StudentPortalApplication]


class StudentDashboardProfile(Schema):
    full_name: str
    email: str
    student_ref: str
    institution: str


class StudentApplicationCounts(Schema):
    total: int
    draft: int
    submitted: int
    under_review: int
    additional_information: int
    approved: int
    rejected: int
    withdrawn: int


class StudentInformationRequest(Schema):
    application_id: uuid.UUID
    reference: str
    program: str | None
    message: str | None
    requested_at: datetime | None


class StudentActivityItem(Schema):
    kind: Literal["status_change", "document_review"]
    application_id: uuid.UUID
    reference: str
    title: str
    detail: str | None
    occurred_at: datetime


class StudentDashboardOut(Schema):
    profile: StudentDashboardProfile
    counts: StudentApplicationCounts
    information_requests: list[StudentInformationRequest]
    recent_activity: list[StudentActivityItem]
    applications: list[StudentPortalApplication]
