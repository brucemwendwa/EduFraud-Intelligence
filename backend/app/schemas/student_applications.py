from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.common import Schema


class StudentApplicationDraft(Schema):
    award_year: str | None = Field(default=None, pattern=r"^20\d{2}-20\d{2}$")
    dependency_status: Literal["dependent", "independent"] | None = None
    enrollment_intensity: Literal["full_time", "three_quarter_time", "half_time", "less_than_half_time"] | None = None
    program: str | None = Field(default=None, max_length=120)
    requested_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    student_aid_index: int | None = Field(default=None, ge=-1500, le=999999)


class StudentApplicationSubmit(Schema):
    """Optional covering note, used when responding to a request for additional information."""

    response_note: str | None = Field(default=None, max_length=1000)


class StudentApplicationHistory(Schema):
    """Student-safe lifecycle entry. Staff-only review notes and staff roles are never included."""

    from_status: str | None
    to_status: str
    actor_role: Literal["student", "financial_aid_office"]
    student_message: str | None
    created_at: datetime


class StudentStatusMessage(Schema):
    """What the financial aid office told the student about the application's current status."""

    status: str
    message: str | None
    created_at: datetime


class StudentApplicationOut(Schema):
    id: uuid.UUID
    reference: str
    award_year: str | None
    status: str
    submitted_at: datetime | None
    dependency_status: str | None
    enrollment_intensity: str | None
    program: str | None
    requested_amount: Decimal | None
    student_aid_index: int | None
    is_editable: bool
    is_withdrawable: bool
    outstanding_requirements: list[str]
    status_message: StudentStatusMessage | None
    history: list[StudentApplicationHistory]
