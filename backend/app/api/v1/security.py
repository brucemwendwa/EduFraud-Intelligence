"""Device & Access Intelligence: sign-ins, devices, credential and recovery events."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.core.errors import ConflictError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import Device, SecurityEvent, Student, StudentFinancialAccount
from app.models.enums import AuditCategory, RiskLevel, SecurityEventType
from app.schemas.accounts import DeviceOut, DeviceTrustIn, SecurityEventRow, SecuritySummary
from app.schemas.common import Page, Pagination
from app.services import account_views, accounts, audit

router = APIRouter(prefix="/security", tags=["device & access intelligence"])

Reader = Annotated[Principal, Depends(require(P.SECURITY_READ))]
_E = SecurityEventType


@router.get("/events", response_model=Page[SecurityEventRow], summary="Account security events")
def list_events(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    q: Annotated[str | None, Query(max_length=60, description="SEV-, SFA- or STU- reference")] = None,
    event_type: Annotated[list[SecurityEventType] | None, Query()] = None,
    outcome: Annotated[str | None, Query(max_length=16, pattern=r"^[a-z_]+$")] = None,
    elevated: bool | None = None,
    account_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    direction: Literal["asc", "desc"] = "desc",
) -> Page[SecurityEventRow]:
    stmt = scoped(select(SecurityEvent), SecurityEvent, principal)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = (
            stmt.join(Student, Student.id == SecurityEvent.student_id)
            .outerjoin(StudentFinancialAccount, StudentFinancialAccount.id == SecurityEvent.account_id)
            .where(
                or_(
                    func.lower(SecurityEvent.reference).like(like),
                    func.lower(Student.student_ref).like(like),
                    func.lower(StudentFinancialAccount.reference).like(like),
                )
            )
        )
    if event_type:
        stmt = stmt.where(SecurityEvent.event_type.in_([t.value for t in event_type]))
    if outcome:
        stmt = stmt.where(SecurityEvent.outcome == outcome)
    if elevated is not None:
        levels = [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        stmt = stmt.where(SecurityEvent.risk_level.in_(levels) if elevated else SecurityEvent.risk_level.not_in(levels))
    if account_id:
        stmt = stmt.where(SecurityEvent.account_id == account_id)
    if device_id:
        stmt = stmt.where(SecurityEvent.device_id == device_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = SecurityEvent.occurred_at.desc() if direction == "desc" else SecurityEvent.occurred_at.asc()
    rows = db.scalars(
        stmt.order_by(order, SecurityEvent.reference.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(
        items=account_views.security_event_rows(db, principal, list(rows)),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


def _shared_tokens(db: DB, principal: Principal) -> dict[str, int]:
    since = utcnow() - timedelta(days=30)
    stmt = (
        select(Device.device_token, func.count(func.distinct(Device.student_id)))
        .where(Device.is_shared_kiosk.is_(False), Device.last_seen_at >= since)
        .group_by(Device.device_token)
        .having(func.count(func.distinct(Device.student_id)) >= 2)
    )
    shared = dict(db.execute(stmt).all())
    if principal.org_id is not None and shared:
        visible = set(
            db.scalars(
                select(Device.device_token).where(
                    Device.device_token.in_(shared), Device.organization_id == principal.org_id
                )
            )
        )
        shared = {t: n for t, n in shared.items() if t in visible}
    return shared


@router.get("/summary", response_model=SecuritySummary, summary="Access-security summary (last 30 days)")
def summary(db: DB, principal: Reader) -> SecuritySummary:
    since = utcnow() - timedelta(days=30)
    rows = db.execute(
        scoped(select(SecurityEvent.event_type, SecurityEvent.risk_level), SecurityEvent, principal).where(
            SecurityEvent.occurred_at >= since
        )
    ).all()
    by_type = Counter(r.event_type for r in rows)
    return SecuritySummary(
        window_days=30,
        events=len(rows),
        by_type=dict(by_type),
        new_devices=by_type.get(_E.NEW_DEVICE_LOGIN, 0),
        failed_logins=by_type.get(_E.LOGIN_FAILED, 0),
        password_resets=by_type.get(_E.PASSWORD_RESET_REQUESTED, 0) + by_type.get(_E.ACCOUNT_RECOVERY_REQUESTED, 0),
        shared_devices=len(_shared_tokens(db, principal)),
        elevated_events=sum(1 for r in rows if r.risk_level in ("medium", "high", "critical")),
    )


@router.get("/devices", response_model=Page[DeviceOut], summary="Devices seen on student accounts")
def list_devices(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    trust_status: Annotated[str | None, Query(pattern="^(trusted|unfamiliar|suspicious)$")] = None,
    shared: bool | None = None,
    q: Annotated[str | None, Query(max_length=60, description="STU- reference or device label")] = None,
) -> Page[DeviceOut]:
    stmt = scoped(select(Device), Device, principal).join(Student, Student.id == Device.student_id)
    if trust_status:
        stmt = stmt.where(Device.trust_status == trust_status)
    if shared:
        stmt = stmt.where(Device.device_token.in_(list(_shared_tokens(db, principal))))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Student.student_ref).like(like), func.lower(Device.label).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Device.last_seen_at.desc()).offset(paging.offset).limit(paging.page_size)).all()
    return Page(
        items=account_views.device_rows(db, principal, list(rows)),
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.post(
    "/devices/{device_id}/trust",
    response_model=DeviceOut,
    summary="Mark a device trusted or suspicious (audited; re-scores the account)",
)
def set_trust(
    device_id: uuid.UUID,
    body: DeviceTrustIn,
    request: Request,
    db: DB,
    principal: Annotated[Principal, Depends(require(P.ACCOUNTS_RESTRICT))],
) -> DeviceOut:
    device = get_scoped_or_404(db, Device, device_id, principal, "Device")
    if device.trust_status == body.trust_status:
        raise ConflictError(f"The device is already {body.trust_status}.")
    previous = device.trust_status
    device.trust_status, device.trust_reason = body.trust_status, body.reason
    audit.record(
        db,
        category=AuditCategory.SECURITY,
        action="device.trust_change",
        actor=principal.user,
        organization_id=device.organization_id,
        target_type="device",
        target_id=device.id,
        target_ref=device.label,
        details={"from": previous, "to": body.trust_status, "reason": body.reason},
        request=request,
    )
    account = db.scalar(select(StudentFinancialAccount).where(StudentFinancialAccount.student_id == device.student_id))
    if account is not None:
        accounts.reassess(db, account, triggered_by="user", user=principal.user)
    db.commit()
    db.refresh(device)
    return account_views.device_rows(db, principal, [device])[0]
