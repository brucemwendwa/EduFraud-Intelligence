"""Schemas for authentication, users, roles and institutions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import OrgRef, Schema


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RoleRef(Schema):
    key: str
    name: str


class Me(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    title: str | None
    role: RoleRef
    organization: OrgRef | None
    is_platform_admin: bool
    permissions: list[str]
    accessible_organizations: list[OrgRef]


class TokenResponse(Schema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_at: datetime


class DemoAccount(Schema):
    email: str
    full_name: str
    role_key: str
    role_name: str
    organization_name: str | None


class ChangePasswordRequest(Schema):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class PermissionOut(Schema):
    key: str
    description: str
    category: str


class RoleOut(Schema):
    id: uuid.UUID
    key: str
    name: str
    description: str
    is_platform_role: bool
    permissions: list[PermissionOut]


class UserOut(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    title: str | None
    role: RoleRef
    organization: OrgRef | None
    is_active: bool
    is_demo: bool
    last_login_at: datetime | None
    locked_until: datetime | None
    created_at: datetime


class UserCreate(Schema):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    role_key: str = Field(max_length=40)
    organization_id: uuid.UUID | None = None
    password: str = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserUpdate(Schema):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    role_key: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None
    unlock: bool | None = None


class OrganizationOut(Schema):
    id: uuid.UUID
    name: str
    slug: str
    institution_type: str
    city: str
    state: str
    synthetic_ope_id: str
    is_active: bool
    is_synthetic: bool
    created_at: datetime


class OrganizationStats(OrganizationOut):
    user_count: int
    application_count: int
    open_alert_count: int


class OrganizationCreate(Schema):
    name: str = Field(min_length=3, max_length=160)
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9-]+$")
    institution_type: Literal["public_4yr", "private_4yr", "community_college", "technical"]
    city: str = Field(min_length=2, max_length=80)
    state: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")


class OrganizationUpdate(Schema):
    name: str | None = Field(default=None, min_length=3, max_length=160)
    city: str | None = Field(default=None, min_length=2, max_length=80)
    is_active: bool | None = None
