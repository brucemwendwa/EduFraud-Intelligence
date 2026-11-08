"""Invitation-based staff onboarding, scoped to one institution."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.api.v1.users import assignable_role
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError, ValidationFailedError
from app.core.permissions import P
from app.core.ratelimit import activation_limiter
from app.core.security import hash_password, password_problems
from app.db.types import utcnow
from app.models import Organization, StaffInvitation, User
from app.models.enums import AuditCategory
from app.schemas.identity import (
    StaffActivationOut,
    StaffActivationRequest,
    StaffInvitationCreate,
    StaffInvitationOut,
)
from app.services import audit, email_templates
from app.services.mailer import get_mailer

router = APIRouter(tags=["users"])
_INVALID_LINK = "This activation link is invalid or has expired."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _activation_url(token: str) -> str:
    return f"{get_settings().public_app_url}/activate-staff?{urlencode({'token': token})}"


def _out(invitation: StaffInvitation, token: str | None = None) -> StaffInvitationOut:
    settings = get_settings()
    return StaffInvitationOut(
        id=invitation.id,
        email=invitation.email,
        full_name=invitation.full_name,
        title=invitation.title,
        role_key=invitation.role.key,
        role_name=invitation.role.name,
        expires_at=invitation.expires_at,
        used_at=invitation.used_at,
        revoked_at=invitation.revoked_at,
        created_at=invitation.created_at,
        activation_url=_activation_url(token) if token and not settings.is_production else None,
    )


@router.get("/staff-invitations", response_model=list[StaffInvitationOut], summary="Pending staff invitations")
def list_invitations(
    db: DB, principal: Annotated[Principal, Depends(require(P.USERS_READ))]
) -> list[StaffInvitationOut]:
    now = utcnow()
    rows = db.scalars(
        scoped(select(StaffInvitation), StaffInvitation, principal)
        .where(
            StaffInvitation.used_at.is_(None),
            StaffInvitation.revoked_at.is_(None),
            StaffInvitation.expires_at > now,
        )
        .order_by(StaffInvitation.created_at.desc())
    ).all()
    return [_out(row) for row in rows]


@router.post("/staff-invitations", response_model=StaffInvitationOut, status_code=201, summary="Invite a staff member")
def create_invitation(
    body: StaffInvitationCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> StaffInvitationOut:
    role = assignable_role(db, principal, body.role_key)
    if role.is_platform_role:
        raise ForbiddenError("Platform roles cannot be granted by invitation.")
    organization_id = principal.org_id
    if organization_id is None:
        raise ValidationFailedError("Choose the institution this person will join.")
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise ValidationFailedError("Institution is unavailable.")
    if db.scalar(select(User.id).where(func.lower(User.email) == body.email)) is not None:
        raise ConflictError("A user with this email already exists.")

    now = utcnow()
    for existing in db.scalars(
        select(StaffInvitation).where(
            StaffInvitation.organization_id == organization_id,
            func.lower(StaffInvitation.email) == body.email,
            StaffInvitation.used_at.is_(None),
            StaffInvitation.revoked_at.is_(None),
        )
    ):
        existing.revoked_at = now  # a new invitation replaces any outstanding link

    token = secrets.token_urlsafe(32)
    invitation = StaffInvitation(
        organization_id=organization_id,
        role_id=role.id,
        email=body.email,
        full_name=body.full_name,
        title=body.title,
        token_hash=_hash(token),
        expires_at=now + timedelta(hours=get_settings().student_invitation_ttl_hours),
        invited_by_user_id=principal.user.id,
    )
    db.add(invitation)
    db.flush()
    try:
        get_mailer().send(
            recipient=invitation.email,
            content=email_templates.staff_invitation(
                organization_name=organization.name, role_name=role.name, activation_url=_activation_url(token)
            ),
        )
    except Exception as exc:  # noqa: BLE001 - never leave a usable but undelivered link
        db.rollback()
        raise ValidationFailedError("Invitation email could not be delivered. Please try again.") from exc
    audit.record(
        db,
        category=AuditCategory.PERMISSION,
        action="user.invite",
        actor=principal.user,
        organization_id=organization_id,
        target_type="staff_invitation",
        target_id=invitation.id,
        target_ref=invitation.email,
        details={"role": role.key},
        request=request,
    )
    db.commit()
    db.refresh(invitation)
    return _out(invitation, token)


@router.post(
    "/staff-invitations/{invitation_id}/revoke", response_model=StaffInvitationOut, summary="Revoke an invitation"
)
def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> StaffInvitationOut:
    invitation = get_scoped_or_404(db, StaffInvitation, invitation_id, principal, "Invitation")
    if invitation.used_at is not None or invitation.revoked_at is not None:
        raise ConflictError("This invitation can no longer be revoked.")
    invitation.revoked_at = utcnow()
    audit.record(
        db,
        category=AuditCategory.PERMISSION,
        action="user.invitation_revoke",
        actor=principal.user,
        organization_id=invitation.organization_id,
        target_type="staff_invitation",
        target_id=invitation.id,
        target_ref=invitation.email,
        request=request,
    )
    db.commit()
    db.refresh(invitation)
    return _out(invitation)


@router.post("/staff-activation", response_model=StaffActivationOut, summary="Activate an invited staff account")
def activate_staff(body: StaffActivationRequest, request: Request, db: DB) -> StaffActivationOut:
    client = request.client.host if request.client else "unknown"
    if not activation_limiter.allow(client):
        raise UnauthorizedError(_INVALID_LINK)
    problems = password_problems(body.password)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.", details=[{"field": "password", "message": p} for p in problems]
        )
    now = utcnow()
    invitation = db.scalar(select(StaffInvitation).where(StaffInvitation.token_hash == _hash(body.token)))
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= now
        or db.scalar(select(User.id).where(func.lower(User.email) == invitation.email)) is not None
    ):
        raise UnauthorizedError(_INVALID_LINK)
    user = User(
        organization_id=invitation.organization_id,
        role_id=invitation.role_id,
        email=invitation.email,
        full_name=invitation.full_name,
        title=invitation.title,
        password_hash=hash_password(body.password),
        is_active=True,
        is_demo=False,
        password_changed_at=now,
    )
    db.add(user)
    db.flush()
    invitation.used_at = now
    audit.record(
        db,
        category=AuditCategory.PERMISSION,
        action="user.activation",
        actor=user,
        organization_id=invitation.organization_id,
        target_type="user",
        target_id=user.id,
        target_ref=user.email,
        details={"role": invitation.role.key},
        request=request,
    )
    db.commit()
    return StaffActivationOut(email=user.email, full_name=user.full_name)
