from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.api.deps import DB, CurrentPrincipal, _extract_token, get_current_user
from app.core.client import client_address
from app.core.config import get_settings
from app.core.errors import AppError, LockedError, UnauthorizedError, ValidationFailedError
from app.core.ratelimit import login_limiter, password_reset_limiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    password_problems,
    verify_password,
)
from app.db.types import utcnow
from app.models import Organization, PasswordResetToken, RevokedSession, User
from app.models.enums import AuditCategory, AuditOutcome
from app.schemas.common import OrgRef
from app.schemas.identity import (
    ChangePasswordRequest,
    DemoAccount,
    LoginRequest,
    Me,
    PasswordResetAccepted,
    PasswordResetConfirm,
    PasswordResetRequest,
    RoleRef,
    TokenResponse,
)
from app.seed.base import DEMO_PRESENTER_EMAIL
from app.services import audit, email_templates
from app.services.mailer import get_mailer

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID = "Invalid email or password."
_INVALID_RESET = "This password reset link is invalid or has expired."
_RESET_REQUEST_COOLDOWN = timedelta(minutes=1)
logger = logging.getLogger("edushield.auth")


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
        is_demo=user.is_demo,
        permissions=sorted(user.permission_keys),
        accessible_organizations=[OrgRef.model_validate(o) for o in orgs],
    )


def _authenticate(db: DB, request: Request, email: str, password: str) -> User:
    settings = get_settings()
    client = client_address(request)
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


def _revoke_presented_session(db: DB, request: Request) -> None:
    """Ends this session on the server, so a copied token stops working before it would expire."""
    token = _extract_token(request)
    if not token:
        return
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError:
        return
    if db.get(RevokedSession, claims["jti"]) is None:
        db.add(RevokedSession(jti=claims["jti"], expires_at=datetime.fromtimestamp(claims["exp"], UTC)))


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
        secure=settings.is_hardened,
        samesite="strict",
        path="/api",
    )
    return build_me(db, user)


@router.post("/demo-login", response_model=Me, summary="Start the restricted synthetic demo session")
def demo_login(request: Request, response: Response, db: DB) -> Me:
    """Explicit development-only synthetic demo session."""
    settings = get_settings()
    if not settings.demo_mode:
        raise UnauthorizedError(_INVALID)
    user = db.scalar(select(User).where(User.email == DEMO_PRESENTER_EMAIL, User.is_demo, User.is_active))
    if user is None:
        raise UnauthorizedError(_INVALID)
    user.last_login_at = utcnow()
    audit.record(db, category=AuditCategory.AUTHENTICATION, action="auth.demo_login", actor=user, request=request)
    db.commit()
    token, expires = create_access_token(user.id)
    response.set_cookie(
        settings.session_cookie_name, token, max_age=settings.access_token_ttl_minutes * 60,
        expires=expires, httponly=True, secure=settings.is_hardened, samesite="strict", path="/api",
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
        _revoke_presented_session(db, request)
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


def _reset_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _client_key(request: Request) -> str:
    return client_address(request)


def _send_password_reset(recipient: str, token: str) -> None:
    """Runs after the response, so response time does not reveal whether the account exists."""
    settings = get_settings()
    try:
        get_mailer(settings).send(
            recipient=recipient,
            content=email_templates.password_reset(
                reset_url=f"{settings.public_app_url}/reset-password?token={token}",
                ttl_minutes=settings.password_reset_ttl_minutes,
            ),
        )
    except Exception:  # noqa: BLE001 - the requester always gets the same response
        logger.warning("password_reset_delivery_failed")


@router.post(
    "/password-reset/request",
    response_model=PasswordResetAccepted,
    status_code=202,
    summary="Request a password reset link (the response never reveals whether the account exists)",
)
def request_password_reset(
    body: PasswordResetRequest, request: Request, background: BackgroundTasks, db: DB
) -> PasswordResetAccepted:
    if not password_reset_limiter.allow(_client_key(request)):
        raise TooManyRequestsError("Too many requests. Please wait a minute and try again.")
    now = utcnow()
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    eligible = user is not None and user.is_active and not user.is_demo
    token: str | None = None
    if eligible:
        latest = db.scalar(
            select(func.max(PasswordResetToken.created_at)).where(PasswordResetToken.user_id == user.id)
        )
        if latest is None or latest <= now - _RESET_REQUEST_COOLDOWN:
            for existing in db.scalars(
                select(PasswordResetToken).where(
                    PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
                )
            ):
                existing.used_at = now
            token = secrets.token_urlsafe(32)
            db.add(
                PasswordResetToken(
                    user_id=user.id,
                    token_hash=_reset_token_hash(token),
                    expires_at=now + timedelta(minutes=get_settings().password_reset_ttl_minutes),
                )
            )
    audit.record(
        db,
        category=AuditCategory.AUTHENTICATION,
        action="auth.password_reset_requested",
        actor=user if eligible else None,
        details={"link_issued": token is not None},
        request=request,
    )
    db.commit()
    if token and user is not None:
        background.add_task(_send_password_reset, user.email, token)
    return PasswordResetAccepted()


@router.post("/password-reset/confirm", status_code=204, summary="Set a new password with a single-use reset link")
def confirm_password_reset(body: PasswordResetConfirm, request: Request, response: Response, db: DB) -> Response:
    if not password_reset_limiter.allow(_client_key(request)):
        raise TooManyRequestsError("Too many requests. Please wait a minute and try again.")
    problems = password_problems(body.password)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.", details=[{"field": "password", "message": p} for p in problems]
        )
    now = utcnow()
    record = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == _reset_token_hash(body.token)))
    if record is None or record.used_at is not None or record.expires_at <= now:
        raise UnauthorizedError(_INVALID_RESET)
    user = db.get(User, record.user_id)
    if user is None or not user.is_active or user.is_demo:
        raise UnauthorizedError(_INVALID_RESET)
    record.used_at = now
    user.password_hash = hash_password(body.password)
    user.password_changed_at = now  # ends every existing session
    user.failed_login_attempts = 0
    user.locked_until = None
    audit.record(
        db, category=AuditCategory.AUTHENTICATION, action="auth.password_reset_completed", actor=user, request=request
    )
    db.commit()
    response.status_code = 204
    return response


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
