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


class StudentApplicationHistory(Schema):
    from_status: str | None
    to_status: str
    actor_role: str
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
    risk_level: str | None
    is_editable: bool
    outstanding_requirements: list[str]
    history: list[StudentApplicationHistory]
