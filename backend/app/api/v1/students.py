from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import DB, Principal, get_scoped_or_404, require
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Student
from app.models.enums import AuditCategory
from app.schemas.aid import RevealRequest, RevealResponse
from app.services import audit

router = APIRouter(prefix="/students", tags=["students"])


@router.post(
    "/{student_id}/reveal",
    response_model=RevealResponse,
    summary="Reveal a masked student name (justification required; recorded as a data-access event)",
)
def reveal_student(
    student_id: uuid.UUID,
    body: RevealRequest,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.PII_REVEAL))],
) -> RevealResponse:
    stu = get_scoped_or_404(db, Student, student_id, principal, "Student")
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="student.pii_reveal",
        actor=principal.user,
        organization_id=stu.organization_id,
        target_type="student",
        target_id=stu.id,
        target_ref=stu.student_ref,
        details={"fields": ["first_name", "last_name"], "reason": body.reason},
        request=request,
    )
    db.commit()
    return RevealResponse(student_id=stu.id, first_name=stu.first_name, last_name=stu.last_name, revealed_at=utcnow())
