"""Synchronises the code-defined permission catalogue and roles into the database (idempotent)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_DESCRIPTIONS, ROLES
from app.models import Permission, Role


def sync_rbac(db: Session) -> dict[str, Role]:
    perms = {p.key: p for p in db.scalars(select(Permission))}
    for key, (category, description) in PERMISSION_DESCRIPTIONS.items():
        perm = perms.get(key.value)
        if perm is None:
            perm = Permission(key=key.value, category=category, description=description)
            db.add(perm)
            perms[key.value] = perm
        else:
            perm.category, perm.description = category, description

    roles = {r.key: r for r in db.scalars(select(Role))}
    for definition in ROLES:
        role = roles.get(definition.key)
        if role is None:
            role = Role(key=definition.key)
            db.add(role)
            roles[definition.key] = role
        role.name = definition.name
        role.description = definition.description
        role.is_platform_role = definition.is_platform_role
        role.permissions = sorted((perms[p.value] for p in definition.permissions), key=lambda p: p.key)
    db.flush()
    return roles
