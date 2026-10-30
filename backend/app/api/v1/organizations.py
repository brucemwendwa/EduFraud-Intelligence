from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, Principal, require
from app.core.errors import ConflictError, NotFoundError
from app.core.permissions import P
from app.models import Alert, FinancialAidApplication, Organization, User
from app.models.enums import AlertStatus, AuditCategory
from app.schemas.identity import OrganizationCreate, OrganizationOut, OrganizationStats, OrganizationUpdate
from app.services import audit

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _visible(db: DB, principal: Principal) -> list[Organization]:
    stmt = select(Organization).order_by(Organization.name)
    if not principal.is_platform_admin:
        stmt = stmt.where(Organization.id == principal.user.organization_id)
    return list(db.scalars(stmt))


def _counts(db: DB, model: type, *where) -> dict[uuid.UUID, int]:  # type: ignore[no-untyped-def]
    stmt = select(model.organization_id, func.count()).group_by(model.organization_id)  # type: ignore[attr-defined]
    for clause in where:
        stmt = stmt.where(clause)
    return dict(db.execute(stmt).all())  # type: ignore[arg-type]


@router.get("", response_model=list[OrganizationStats], summary="Institutions visible to the current user")
def list_organizations(
    db: DB, principal: Annotated[Principal, Depends(require(P.DASHBOARD_READ))]
) -> list[OrganizationStats]:
    users = _counts(db, User)
    apps = _counts(db, FinancialAidApplication)
    alerts = _counts(db, Alert, Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]))
    return [
        OrganizationStats(
            **OrganizationOut.model_validate(o).model_dump(),
            user_count=users.get(o.id, 0),
            application_count=apps.get(o.id, 0),
            open_alert_count=alerts.get(o.id, 0),
        )
        for o in _visible(db, principal)
    ]


@router.post("", response_model=OrganizationOut, status_code=201, summary="Create an institution (platform admin)")
def create_organization(
    body: OrganizationCreate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.ORGS_MANAGE))],
) -> Organization:
    if db.scalar(select(Organization).where((Organization.slug == body.slug) | (Organization.name == body.name))):
        raise ConflictError("An institution with this name or slug already exists.")
    count = db.scalar(select(func.count()).select_from(Organization)) or 0
    org = Organization(**body.model_dump(), synthetic_ope_id=f"SYN-{count + 1:05d}")
    db.add(org)
    db.flush()
    audit.record(
        db,
        category=AuditCategory.SYSTEM,
        action="organization.create",
        actor=principal.user,
        organization_id=org.id,
        target_type="organization",
        target_id=org.id,
        target_ref=org.slug,
        request=request,
    )
    db.commit()
    return org


@router.patch("/{org_id}", response_model=OrganizationOut, summary="Update an institution (platform admin)")
def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.ORGS_MANAGE))],
) -> Organization:
    org = db.get(Organization, org_id)
    if org is None:
        raise NotFoundError("Institution not found.")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(org, field, value)
    audit.record(
        db,
        category=AuditCategory.SYSTEM,
        action="organization.update",
        actor=principal.user,
        organization_id=org.id,
        target_type="organization",
        target_id=org.id,
        target_ref=org.slug,
        details={"changed": sorted(changes)},
        request=request,
    )
    db.commit()
    return org
