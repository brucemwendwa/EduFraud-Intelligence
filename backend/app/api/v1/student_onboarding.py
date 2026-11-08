"""Invitation-only student activation and self-service profile endpoints."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, Principal, get_scoped_or_404, require
from app.core.client import client_address
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError, ValidationFailedError
from app.core.permissions import P
from app.core.ratelimit import activation_limiter
from app.core.security import hash_password, password_problems
from app.db.types import utcnow
from app.models import Organization, Role, Student, StudentInvitation, User
from app.models.enums import AuditCategory
from app.schemas.common import OrgRef
from app.schemas.identity import (
    StudentActivationOut,
    StudentActivationRequest,
    StudentInvitationCreate,
    StudentInvitationOut,
    StudentProfileOut,
    StudentProfileUpdate,
)
from app.services import audit
from app.services.mailer import get_invitation_mailer

router = APIRouter(tags=["student onboarding"])

_INVALID_LINK = "This activation link is invalid or has expired."


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _activation_url(token: str) -> str:
    settings = get_settings()
    return f"{settings.student_activation_base_url}?{urlencode({'token': token})}"


def _invitation_out(invitation: StudentInvitation, token: str | None = None) -> StudentInvitationOut:
    settings = get_settings()
    return StudentInvitationOut(
        id=invitation.id,
        student_id=invitation.student_id,
        email=invitation.email,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        activation_url=_activation_url(token) if token and not settings.is_production else None,
    )


@router.post(
    "/students/{student_id}/invitation",
    response_model=StudentInvitationOut,
    status_code=201,
    summary="Invite an existing student to activate their portal account",
)
def create_invitation(
    student_id: uuid.UUID,
    body: StudentInvitationCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> StudentInvitationOut:
    student = get_scoped_or_404(db, Student, student_id, principal, "Student")
    if db.scalar(select(User.id).where(User.student_id == student.id)) is not None:
        raise ConflictError("This student already has a portal account.")
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email)) is not None:
        raise ConflictError("This email address is already in use.")

    now = utcnow()
    # Re-inviting invalidates every outstanding link for this student before creating a new one.
    for existing in db.scalars(
        select(StudentInvitation).where(
            StudentInvitation.student_id == student.id,
            StudentInvitation.used_at.is_(None),
            StudentInvitation.revoked_at.is_(None),
        )
    ):
        existing.revoked_at = now

    token = secrets.token_urlsafe(32)
    invitation = StudentInvitation(
        organization_id=student.organization_id,
        student_id=student.id,
        email=body.email,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(hours=get_settings().student_invitation_ttl_hours),
        invited_by_user_id=principal.user.id,
    )
    db.add(invitation)
    db.flush()
    organization = db.get(Organization, student.organization_id)
    if organization is None:
        db.rollback()
        raise ValidationFailedError("Student institution is unavailable.")
    try:
        get_invitation_mailer().send_activation(
            recipient=invitation.email,
            student_ref=student.student_ref,
            organization_name=organization.name,
            activation_url=_activation_url(token),
        )
    except Exception as exc:  # noqa: BLE001 - provider failures must not leave a usable but undelivered link
        db.rollback()
        raise ValidationFailedError("Invitation email could not be delivered. Please try again.") from exc
    audit.record(
        db,
        category=AuditCategory.AUTHENTICATION,
        action="student.invitation_create",
        actor=principal.user,
        organization_id=student.organization_id,
        target_type="student",
        target_id=student.id,
        target_ref=student.student_ref,
        details={"email": invitation.email, "expires_at": invitation.expires_at.isoformat()},
        request=request,
    )
    db.commit()
    db.refresh(invitation)
    return _invitation_out(invitation, token)


@router.post(
    "/student-invitations/{invitation_id}/revoke",
    response_model=StudentInvitationOut,
    summary="Revoke an unused student invitation",
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> StudentInvitationOut:
    invitation = get_scoped_or_404(db, StudentInvitation, invitation_id, principal, "Invitation")
    if invitation.used_at is not None or invitation.revoked_at is not None:
        raise ConflictError("This invitation can no longer be revoked.")
    invitation.revoked_at = utcnow()
    audit.record(
        db,
        category=AuditCategory.AUTHENTICATION,
        action="student.invitation_revoke",
        actor=principal.user,
        organization_id=invitation.organization_id,
        target_type="student_invitation",
        target_id=invitation.id,
        target_ref=invitation.email,
        request=request,
    )
    db.commit()
    db.refresh(invitation)
    return _invitation_out(invitation)


@router.post("/student-activation", response_model=StudentActivationOut, summary="Activate an invited student account")
def activate_student(body: StudentActivationRequest, request: Request, db: DB) -> StudentActivationOut:
    if not activation_limiter.allow(client_address(request)):
        raise UnauthorizedError(_INVALID_LINK)
    problems = password_problems(body.password)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.", details=[{"field": "password", "message": p} for p in problems]
        )
    now = utcnow()
    invitation = db.scalar(select(StudentInvitation).where(StudentInvitation.token_hash == _token_hash(body.token)))
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
    ):
        raise UnauthorizedError(_INVALID_LINK)
    student = db.get(Student, invitation.student_id)
    role = db.scalar(select(Role).where(Role.key == "student"))
    if student is None or role is None or student.organization_id != invitation.organization_id:
        raise UnauthorizedError(_INVALID_LINK)
    if db.scalar(select(User.id).where(User.student_id == student.id)) is not None:
        raise UnauthorizedError(_INVALID_LINK)
    if db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)) is not None:
        raise UnauthorizedError(_INVALID_LINK)
    user = User(
        organization_id=student.organization_id,
        student_id=student.id,
        role_id=role.id,
        email=invitation.email,
        full_name=f"{student.first_name} {student.last_name}",
        title=None,
        password_hash=hash_password(body.password),
        is_active=True,
        is_demo=False,
        password_changed_at=now,
    )
    db.add(user)
    db.flush()
    invitation.used_at, invitation.activated_user_id = now, user.id
    audit.record(
        db,
        category=AuditCategory.AUTHENTICATION,
        action="student.activation",
        actor=user,
        organization_id=student.organization_id,
        target_type="student",
        target_id=student.id,
        target_ref=student.student_ref,
        request=request,
    )
    db.commit()
    return StudentActivationOut(email=user.email, full_name=user.full_name)


def _portal_student(db: DB, principal: Principal) -> Student:
    if principal.user.student_id is None:
        raise ForbiddenError("This account is not linked to a student portal record.")
    student = db.get(Student, principal.user.student_id)
    if student is None or student.organization_id != principal.user.organization_id:
        raise ForbiddenError("This student portal record is unavailable.")
    return student


def _profile_out(student: Student, user: User) -> StudentProfileOut:
    assert user.organization is not None
    return StudentProfileOut(
        email=user.email,
        full_name=user.full_name,
        student_ref=student.student_ref,
        organization=OrgRef.model_validate(user.organization),
        state_of_residence=student.state_of_residence,
        biometric_consent=student.biometric_consent,
        biometric_consent_at=student.biometric_consent_at,
        account_status="active" if user.is_active else "inactive",
    )


@router.get("/student-profile/me", response_model=StudentProfileOut, summary="Signed-in student's permitted profile")
def get_profile(db: DB, principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_READ))]) -> StudentProfileOut:
    return _profile_out(_portal_student(db, principal), principal.user)


@router.patch(
    "/student-profile/me", response_model=StudentProfileOut, summary="Update permitted student profile fields"
)
def update_profile(
    body: StudentProfileUpdate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.STUDENT_PORTAL_UPDATE))],
) -> StudentProfileOut:
    student = _portal_student(db, principal)
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationFailedError("Choose at least one profile field to update.")
    if "state_of_residence" in changes:
        student.state_of_residence = changes["state_of_residence"]
    if "biometric_consent" in changes:
        student.biometric_consent = changes["biometric_consent"]
        student.biometric_consent_at = utcnow() if changes["biometric_consent"] else None
    audit.record(
        db,
        category=AuditCategory.DATA_ACCESS,
        action="student.profile_update",
        actor=principal.user,
        organization_id=student.organization_id,
        target_type="student",
        target_id=student.id,
        target_ref=student.student_ref,
        details={"fields": sorted(changes)},
        request=request,
    )
    db.commit()
    db.refresh(student)
    return _profile_out(student, principal.user)
