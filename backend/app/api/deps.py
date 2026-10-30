"""Request-scoped dependencies: database session, authenticated principal, permissions and tenancy."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.permissions import P
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Organization, User
from app.models.enums import AuditCategory, AuditOutcome
from app.services import audit


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DB = Annotated[Session, Depends(get_db)]


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().session_cookie_name)


def get_current_user(request: Request, db: DB) -> User:
    token = _extract_token(request)
    if not token:
        raise UnauthorizedError("Authentication required.")
    try:
        claims = decode_access_token(token)
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError("Your session is invalid or has expired. Please sign in again.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Your session is no longer valid. Please sign in again.")
    if user.password_changed_at and claims["iat"] < int(user.password_changed_at.timestamp()):
        raise UnauthorizedError("Your password was changed. Please sign in again.")
    if user.is_demo and not get_settings().demo_mode:
        raise UnauthorizedError("Demo accounts are disabled.")
    return user


@dataclass(frozen=True)
class Principal:
    """The authenticated user plus the institution scope their request runs under.

    `org_id` is the tenant filter for every scoped query. It is always the user's own
    institution, except for platform administrators, who may select one institution
    (X-Organization-Id) or none (all institutions).
    """

    user: User
    permissions: frozenset[str]
    org_id: uuid.UUID | None

    def can(self, permission: P) -> bool:
        return permission.value in self.permissions

    @property
    def is_platform_admin(self) -> bool:
        return self.user.is_platform_admin


def get_principal(
    db: DB,
    user: Annotated[User, Depends(get_current_user)],
    x_organization_id: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> Principal:
    org_id = user.organization_id
    if user.is_platform_admin:
        org_id = None
        if x_organization_id:
            try:
                requested = uuid.UUID(x_organization_id)
            except ValueError as exc:
                raise NotFoundError("Institution not found.") from exc
            if db.get(Organization, requested) is None:
                raise NotFoundError("Institution not found.")
            org_id = requested
    return Principal(user=user, permissions=frozenset(user.permission_keys), org_id=org_id)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require(*permissions: P) -> Callable[..., Principal]:
    """Dependency factory: the principal must hold every listed permission. Denials are audited."""

    def checker(request: Request, db: DB, principal: CurrentPrincipal) -> Principal:
        missing = [p.value for p in permissions if not principal.can(p)]
        if missing:
            audit.record(
                db,
                category=AuditCategory.PERMISSION,
                action="access.denied",
                outcome=AuditOutcome.DENIED,
                actor=principal.user,
                details={"path": request.url.path, "method": request.method, "missing": missing},
                request=request,
            )
            db.commit()
            raise ForbiddenError("You do not have permission to perform this action.", details={"missing": missing})
        return principal

    return checker


def scoped(stmt: Select, model: type, principal: Principal) -> Select:
    """Applies the tenant filter. Every query on a TenantScoped table must pass through here."""
    if principal.org_id is not None:
        stmt = stmt.where(model.organization_id == principal.org_id)  # type: ignore[attr-defined]
    return stmt


def get_scoped_or_404[ModelT](
    db: Session, model: type[ModelT], obj_id: uuid.UUID, principal: Principal, label: str
) -> ModelT:
    """Fetch by id within the principal's scope. Out-of-scope records are indistinguishable from missing ones."""
    obj = db.get(model, obj_id)
    if obj is None or (principal.org_id is not None and obj.organization_id != principal.org_id):  # type: ignore[attr-defined]
        raise NotFoundError(f"{label} not found.")
    return obj
