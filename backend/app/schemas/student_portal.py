from __future__ import annotations

from decimal import Decimal

from app.schemas.common import Schema


class StudentPortalApplication(Schema):
    reference: str
    status: str
    program: str
    requested_amount: Decimal
    risk_level: str | None


class StudentPortalOut(Schema):
    student_ref: str
    applications: list[StudentPortalApplication]
