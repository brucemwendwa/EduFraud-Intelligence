from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.core.security import hash_password, password_problems
from app.models import Organization, Role, User
from app.models.enums import AuditCategory
from app.schemas.common import Page, Pagination
from app.schemas.identity import RoleOut, UserCreate, UserOut, UserUpdate
from app.services import audit

router = APIRouter(tags=["users"])


@router.get("/roles", response_model=list[RoleOut], summary="Roles and their permissions")
def list_roles(db: DB, _: Annotated[Principal, Depends(require(P.USERS_READ))]) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.is_platform_role.desc(), Role.name)))


@router.get("/users", response_model=Page[UserOut], summary="Users in the current institution scope")
def list_users(
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_READ))],
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[UserOut]:
    stmt = scoped(select(User), User, principal)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.email).like(like), func.lower(User.full_name).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.full_name).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=[UserOut.model_validate(u) for u in rows], total=total, page=paging.page, page_size=paging.page_size
    )


def _assignable_role(db: DB, principal: Principal, role_key: str) -> Role:
    role = db.scalar(select(Role).where(Role.key == role_key))
    if role is None:
        raise ValidationFailedError("Unknown role.", details=[{"field": "role_key", "message": "Unknown role"}])
    if role.is_platform_role and not principal.is_platform_admin:
        raise ForbiddenError("Only platform administrators can grant platform-level roles.")
    return role


@router.post("/users", response_model=UserOut, status_code=201, summary="Create a user")
def create_user(
    body: UserCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> User:
    role = _assignable_role(db, principal, body.role_key)
    if principal.is_platform_admin:
        org_id = None if role.is_platform_role else (body.organization_id or principal.org_id)
        if not role.is_platform_role and (org_id is None or db.get(Organization, org_id) is None):
            raise ValidationFailedError("Choose the institution this user belongs to.")
    else:
        org_id = principal.user.organization_id  # institution admins can only create users in their own institution
    problems = password_problems(body.password)
    if problems:
        raise ValidationFailedError(
            "Password does not meet the policy.", details=[{"field": "password", "message": p} for p in problems]
        )
    if db.scalar(select(User).where(func.lower(User.email) == body.email)):
        raise ConflictError("A user with this email already exists.")

    user = User(
        email=body.email,
        full_name=body.full_name,
        title=body.title,
        role_id=role.id,
        organization_id=org_id,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        category=AuditCategory.PERMISSION,
        action="user.create",
        actor=principal.user,
        organization_id=org_id,
        target_type="user",
        target_id=user.id,
        target_ref=user.email,
        details={"role": role.key},
        request=request,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, summary="Update a user, change role, deactivate or unlock")
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.USERS_MANAGE))],
) -> User:
    if principal.org_id is None and principal.is_platform_admin:
        user = db.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found.")
    else:
        user = get_scoped_or_404(db, User, user_id, principal, "User")
    if user.is_platform_admin and not principal.is_platform_admin:
        raise NotFoundError("User not found.")

    changes = body.model_dump(exclude_unset=True)
    is_self = user.id == principal.user.id
    if is_self and ("role_key" in changes or changes.get("is_active") is False):
        raise ForbiddenError("You cannot change your own role or deactivate your own account.")

    if "role_key" in changes and changes["role_key"] != user.role.key:
        old = user.role.key
        new_role = _assignable_role(db, principal, changes["role_key"])
        user.role_id = new_role.id
        audit.record(
            db,
            category=AuditCategory.PERMISSION,
            action="user.role_change",
            actor=principal.user,
            organization_id=user.organization_id,
            target_type="user",
            target_id=user.id,
            target_ref=user.email,
            details={"from": old, "to": new_role.key},
            request=request,
        )
    if "is_active" in changes and changes["is_active"] != user.is_active:
        user.is_active = bool(changes["is_active"])
        audit.record(
            db,
            category=AuditCategory.PERMISSION,
            action="user.activate" if user.is_active else "user.deactivate",
            actor=principal.user,
            organization_id=user.organization_id,
            target_type="user",
            target_id=user.id,
            target_ref=user.email,
            request=request,
        )
    if changes.get("unlock"):
        user.locked_until = None
        user.failed_login_attempts = 0
        audit.record(
            db,
            category=AuditCategory.AUTHENTICATION,
            action="user.unlock",
            actor=principal.user,
            organization_id=user.organization_id,
            target_type="user",
            target_id=user.id,
            target_ref=user.email,
            request=request,
        )
    for field in ("full_name", "title"):
        if field in changes and changes[field] is not None:
            setattr(user, field, changes[field])
    db.commit()
    db.refresh(user)
    return user
