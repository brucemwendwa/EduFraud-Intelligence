from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.api.deps import DB, CurrentPrincipal, get_current_user
from app.core.config import get_settings
from app.core.errors import AppError, LockedError, UnauthorizedError, ValidationFailedError
from app.core.ratelimit import login_limiter
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    password_problems,
    verify_password,
)
from app.db.types import utcnow
from app.models import Organization, User
from app.models.enums import AuditCategory, AuditOutcome
from app.schemas.common import OrgRef
from app.schemas.identity import ChangePasswordRequest, DemoAccount, LoginRequest, Me, RoleRef, TokenResponse
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID = "Invalid email or password."


class TooManyRequestsError(AppError):
    status_code = 429
    code = "rate_limited"


def build_me(db: DB, user: User) -> Me:
    if user.is_platform_admin:
        orgs = db.scalars(select(Organization).where(Organization.is_active).order_by(Organization.name)).all()
    else:
        orgs = [user.organization] if user.organization else []
    return Me(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        title=user.title,
        role=RoleRef(key=user.role.key, name=user.role.name),
        organization=OrgRef.model_validate(user.organization) if user.organization else None,
        is_platform_admin=user.is_platform_admin,
        permissions=sorted(user.permission_keys),
        accessible_organizations=[OrgRef.model_validate(o) for o in orgs],
    )


def _authenticate(db: DB, request: Request, email: str, password: str) -> User:
    settings = get_settings()
    client = request.client.host if request.client else "unknown"
    if not login_limiter.allow(client):
        raise TooManyRequestsError("Too many sign-in attempts. Please wait a minute and try again.")

    email = email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    now = utcnow()

    def fail(reason: str, outcome: AuditOutcome = AuditOutcome.FAILURE) -> None:
        audit.record(
            db,
            category=AuditCategory.AUTHENTICATION,
            action="auth.login",
            outcome=outcome,
            actor=user,
            details={"reason": reason},
            request=request,
        )
        db.commit()

    if user is None:
        verify_password(None, password)  # equalize timing for unknown accounts
        fail("unknown_account")
        raise UnauthorizedError(_INVALID)
    if user.locked_until and user.locked_until > now:
        fail("account_locked", AuditOutcome.DENIED)
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise LockedError(f"Too many failed attempts. This account is locked for about {minutes} more minute(s).")
    if not user.is_active or (user.is_demo and not settings.demo_mode):
        verify_password(None, password)
        fail("account_disabled", AuditOutcome.DENIED)
        raise UnauthorizedError(_INVALID)
    if not verify_password(user.password_hash, password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_login_attempts = 0
            audit.record(
                db,
                category=AuditCategory.AUTHENTICATION,
                action="auth.lockout",
                outcome=AuditOutcome.DENIED,
                actor=user,
                details={"locked_minutes": settings.lockout_minutes},
                request=request,
            )
        fail("bad_password")
        raise UnauthorizedError(_INVALID)

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    audit.record(db, category=AuditCategory.AUTHENTICATION, action="auth.login", actor=user, request=request)
    db.commit()
    return user


@router.post("/login", response_model=Me, summary="Sign in (sets an httpOnly session cookie)")
def login(body: LoginRequest, request: Request, response: Response, db: DB) -> Me:
    settings = get_settings()
    user = _authenticate(db, request, body.email, body.password)
    token, expires = create_access_token(user.id)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.access_token_ttl_minutes * 60,
        expires=expires,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api",
    )
    return build_me(db, user)


@router.post("/token", response_model=TokenResponse, summary="OAuth2 password flow for API clients and Swagger")
def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: DB) -> TokenResponse:
    user = _authenticate(db, request, form.username, form.password)
    access_token, expires = create_access_token(user.id)
    return TokenResponse(access_token=access_token, expires_at=expires)


@router.post("/logout", status_code=204, summary="Sign out")
def logout(request: Request, response: Response, db: DB) -> Response:
    settings = get_settings()
    try:
        user = get_current_user(request, db)
        audit.record(db, category=AuditCategory.AUTHENTICATION, action="auth.logout", actor=user, request=request)
        db.commit()
    except UnauthorizedError:
        pass
    response.status_code = 204
    response.delete_cookie(settings.session_cookie_name, path="/api", samesite="strict", httponly=True)
    return response


@router.get("/me", response_model=Me, summary="Current user, role, permissions and accessible institutions")
def me(principal: CurrentPrincipal, db: DB) -> Me:
    return build_me(db, principal.user)


@router.get("/demo-accounts", response_model=list[DemoAccount], summary="Synthetic demo accounts (demo mode only)")
def demo_accounts(db: DB) -> list[DemoAccount]:
    if not get_settings().demo_mode:
        return []
    users = db.scalars(select(User).where(User.is_demo, User.is_active)).all()
    # Lead with the accounts used in the documented demo walkthrough.
    featured = [
        "investigator@northbridge.demo",
        "officer@northbridge.demo",
        "inst.admin@northbridge.demo",
        "auditor@northbridge.demo",
        "admin@edushield.demo",
    ]
    users = sorted(users, key=lambda u: (featured.index(u.email) if u.email in featured else 99, u.email))
    return [
        DemoAccount(
            email=u.email,
            full_name=u.full_name,
            role_key=u.role.key,
            role_name=u.role.name,
            organization_name=u.organization.name if u.organization else None,
        )
        for u in users
    ]


@router.post("/change-password", status_code=204, summary="Change your password (revokes existing sessions)")
def change_password(
    body: ChangePasswordRequest, request: Request, response: Response, principal: CurrentPrincipal, db: DB
) -> Response:
    user = principal.user
    if user.is_demo:
        raise ValidationFailedError("Demo account passwords are fixed so every judge can sign in.")
    if not verify_password(user.password_hash, body.current_password):
        audit.record(
            db,
            category=AuditCategory.AUTHENTICATION,
            action="auth.password_change",
            outcome=AuditOutcome.FAILURE,
            actor=user,
            request=request,
        )
        db.commit()
        raise ValidationFailedError("Current password is incorrect.")
    problems = password_problems(body.new_password)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.", details=[{"field": "new_password", "message": p} for p in problems]
        )
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()
    audit.record(db, category=AuditCategory.AUTHENTICATION, action="auth.password_change", actor=user, request=request)
    db.commit()
    response.status_code = 204
    response.delete_cookie(get_settings().session_cookie_name, path="/api", samesite="strict", httponly=True)
    return response
