"""The signed-in student's own aid summary. Every query is restricted to their linked student record."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, Principal, require
from app.core.errors import ForbiddenError
from app.core.permissions import P
from app.models import ApplicationDocument, ApplicationStatusHistory, FinancialAidApplication, Student
from app.models.enums import ApplicationStatus as S
from app.schemas.student_portal import (
    StudentActivityItem,
    StudentApplicationCounts,
    StudentDashboardOut,
    StudentDashboardProfile,
    StudentInformationRequest,
    StudentPortalApplication,
    StudentPortalOut,
)
from app.services.application_lifecycle import STUDENT_EDITABLE

router = APIRouter(prefix="/student-portal", tags=["student portal"])

_RECENT_ACTIVITY = 10
_TITLES = {
    S.DRAFT: "Draft started",
    S.SUBMITTED: "Application submitted",
    S.RECEIVED: "Application received",
    S.IN_REVIEW: "Review started",
    S.ADDITIONAL_INFORMATION_REQUIRED: "Additional information requested",
    S.APPROVED: "Application approved",
    S.REJECTED: "Application not approved",
    S.ON_HOLD: "Application on hold",
    S.WITHDRAWN: "Application withdrawn",
}
_DOCUMENT_TITLES = {
    "accepted": "Document accepted",
    "rejected": "Document not accepted",
    "replacement_requested": "Replacement document requested",
}


def _student(db: DB, principal: Principal) -> Student:
    if principal.user.student_id is None:
        raise ForbiddenError("This account is not linked to a student portal record.")
    student = db.get(Student, principal.user.student_id)
    if student is None or student.organization_id != principal.user.organization_id:
        raise ForbiddenError("This student portal record is unavailable.")
    return student


def _applications(db: DB, student: Student) -> list[FinancialAidApplication]:
    return list(
        db.scalars(
            select(FinancialAidApplication)
            .where(
                FinancialAidApplication.student_id == student.id,
                FinancialAidApplication.organization_id == student.organization_id,
            )
            .order_by(FinancialAidApplication.created_at.desc())
        )
    )


def _row(app: FinancialAidApplication) -> StudentPortalApplication:
    return StudentPortalApplication(
        id=app.id,
        reference=app.reference,
        status=app.status,
        award_year=app.award_year,
        program=app.program,
        requested_amount=app.requested_amount,
        submitted_at=app.submitted_at,
        is_editable=S(app.status) in STUDENT_EDITABLE,
    )


@router.get("/me", response_model=StudentPortalOut, summary="Signed-in student's own aid record")
def me(db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]) -> StudentPortalOut:
    student = _student(db, principal)
    return StudentPortalOut(student_ref=student.student_ref, applications=[_row(a) for a in _applications(db, student)])


@router.get("/dashboard", response_model=StudentDashboardOut, summary="Signed-in student's dashboard")
def dashboard(db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]) -> StudentDashboardOut:
    student = _student(db, principal)
    apps = _applications(db, student)
    by_id = {a.id: a for a in apps}

    def count(*statuses: S) -> int:
        return sum(1 for a in apps if S(a.status) in statuses)

    counts = StudentApplicationCounts(
        total=len(apps),
        draft=count(S.DRAFT),
        submitted=count(S.SUBMITTED, S.RECEIVED),
        under_review=count(S.IN_REVIEW, S.ON_HOLD),
        additional_information=count(S.ADDITIONAL_INFORMATION_REQUIRED),
        approved=count(S.APPROVED),
        rejected=count(S.REJECTED),
        withdrawn=count(S.WITHDRAWN),
    )

    history = (
        list(
            db.scalars(
                select(ApplicationStatusHistory)
                .where(ApplicationStatusHistory.application_id.in_(by_id))
                .order_by(ApplicationStatusHistory.created_at.desc())
            )
        )
        if by_id
        else []
    )
    changes = [h for h in history if h.from_status != h.to_status]

    requests = []
    for app in apps:
        if S(app.status) != S.ADDITIONAL_INFORMATION_REQUIRED:
            continue
        latest = next((h for h in changes if h.application_id == app.id and h.to_status == app.status), None)
        requests.append(
            StudentInformationRequest(
                application_id=app.id,
                reference=app.reference,
                program=app.program,
                message=latest.student_message if latest else None,
                requested_at=latest.created_at if latest else None,
            )
        )

    activity = [
        StudentActivityItem(
            kind="status_change",
            application_id=h.application_id,
            reference=by_id[h.application_id].reference,
            title=_TITLES[S(h.to_status)],
            detail=h.student_message,
            occurred_at=h.created_at,
        )
        for h in changes[:_RECENT_ACTIVITY]
    ]
    if by_id:
        reviewed = db.scalars(
            select(ApplicationDocument)
            .where(ApplicationDocument.application_id.in_(by_id), ApplicationDocument.reviewed_at.is_not(None))
            .order_by(ApplicationDocument.reviewed_at.desc())
            .limit(_RECENT_ACTIVITY)
        )
        for doc in reviewed:
            title = _DOCUMENT_TITLES.get(doc.review_status)
            if title and doc.reviewed_at:
                activity.append(
                    StudentActivityItem(
                        kind="document_review",
                        application_id=doc.application_id,
                        reference=by_id[doc.application_id].reference,
                        title=title,
                        detail=doc.review_reason if doc.review_status != "accepted" else doc.original_filename,
                        occurred_at=doc.reviewed_at,
                    )
                )
    activity.sort(key=lambda item: item.occurred_at, reverse=True)

    assert principal.user.organization is not None
    return StudentDashboardOut(
        profile=StudentDashboardProfile(
            full_name=principal.user.full_name,
            email=principal.user.email,
            student_ref=student.student_ref,
            institution=principal.user.organization.name,
        ),
        counts=counts,
        information_requests=requests,
        recent_activity=activity[:_RECENT_ACTIVITY],
        applications=[_row(a) for a in apps],
    )
