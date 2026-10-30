"""Institutions, users and role-based access control."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Synthetic, Timestamps, UUIDPrimaryKey


class Organization(UUIDPrimaryKey, Timestamps, Synthetic, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), unique=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    institution_type: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(80))
    state: Mapped[str] = mapped_column(String(2))
    # Fictional identifier in the style of an OPE ID; never a real institution code.
    synthetic_ope_id: Mapped[str] = mapped_column(String(16), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(UUIDPrimaryKey, Base):
    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))


class Role(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "roles"

    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    is_platform_role: Mapped[bool] = mapped_column(default=False)

    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email"),)

    # NULL only for platform administrators, who are not bound to one institution.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_demo: Mapped[bool] = mapped_column(default=False)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]

    role: Mapped[Role] = relationship(lazy="joined")
    organization: Mapped[Organization | None] = relationship(lazy="joined")

    @property
    def permission_keys(self) -> set[str]:
        return {p.key for p in self.role.permissions}

    @property
    def is_platform_admin(self) -> bool:
        return self.role.is_platform_role
