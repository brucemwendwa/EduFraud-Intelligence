from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, Principal, require
from app.core.errors import ForbiddenError
from app.core.permissions import P
from app.models import FinancialAidApplication, Student
from app.schemas.student_portal import StudentPortalApplication, StudentPortalOut

router = APIRouter(prefix="/student-portal", tags=["student portal"])


@router.get("/me", response_model=StudentPortalOut, summary="Signed-in student's own synthetic aid record")
def me(db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]) -> StudentPortalOut:
    if principal.user.student_id is None:
        raise ForbiddenError("This account is not linked to a student portal record.")
    student = db.get(Student, principal.user.student_id)
    if student is None or student.organization_id != principal.user.organization_id:
        raise ForbiddenError("This student portal record is unavailable.")
    apps = db.scalars(
        select(FinancialAidApplication)
        .where(FinancialAidApplication.student_id == student.id)
        .order_by(FinancialAidApplication.submitted_at.desc())
    ).all()
    return StudentPortalOut(
        student_ref=student.student_ref,
        applications=[
            StudentPortalApplication(
                reference=a.reference,
                status=a.status,
                program=a.program,
                requested_amount=a.requested_amount,
                risk_level=a.risk_level,
            )
            for a in apps
        ],
    )
