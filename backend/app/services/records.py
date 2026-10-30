"""Builds API views of aid records: masking, token handles and cross-record relationships."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal
from app.core.tokenization import display_token
from app.models import (
    Alert,
    Disbursement,
    FinancialAidApplication,
    Organization,
    PaymentDestinationToken,
    Student,
    StudentIdentityToken,
)
from app.models.enums import AlertStatus
from app.schemas.aid import (
    ApplicationRow,
    DestinationOut,
    DisbursementRow,
    IdentityTokenOut,
    RelatedApplication,
    RelatedGroup,
    StudentRef,
)
from app.schemas.common import OrgRef

TOKEN_LABELS = {
    "ssn": "Shared SSN token",
    "phone": "Shared phone number",
    "email": "Shared email address",
    "address": "Shared mailing address",
    "device": "Shared device fingerprint",
    "ip": "Shared network address",
    "destination": "Shared payment destination",
}
_RELATABLE_TOKENS = ("ssn", "phone", "email", "address")


def mask_name(first: str, last: str) -> str:
    return f"{first[:1]}*** {last[:1]}***"


def student_ref(stu: Student) -> StudentRef:
    return StudentRef(id=stu.id, student_ref=stu.student_ref, masked_name=mask_name(stu.first_name, stu.last_name))


def org_map(db: Session) -> dict[uuid.UUID, Organization]:
    return {o.id: o for o in db.scalars(select(Organization))}


def destination_out(dest: PaymentDestinationToken) -> DestinationOut:
    return DestinationOut(
        id=dest.id,
        handle=display_token(dest.token_value, "DST"),
        destination_type=dest.destination_type,
        display_suffix=dest.display_suffix,
    )


def disbursement_rows(db: Session, rows: list[Disbursement]) -> list[DisbursementRow]:
    orgs = org_map(db)
    app_ids = {d.application_id for d in rows if d.application_id}
    refs = dict(
        db.execute(
            select(FinancialAidApplication.id, FinancialAidApplication.reference).where(
                FinancialAidApplication.id.in_(app_ids)
            )
        ).all()
    )
    return [
        DisbursementRow(
            id=d.id,
            reference=d.reference,
            organization=OrgRef.model_validate(orgs[d.organization_id]),
            student=student_ref(d.student),
            application_id=d.application_id,
            application_ref=refs.get(d.application_id),
            fund_type=d.fund_type,
            amount=d.amount,
            disbursed_at=d.disbursed_at,
            status=d.status,
            destination=destination_out(d.destination),
            destination_changed_at=d.destination_changed_at,
            risk_score=d.risk_score,
            risk_flags=list(d.risk_flags or []),
            hold_reason=d.hold_reason,
            held_at=d.held_at,
        )
        for d in rows
    ]


def open_alert_counts(db: Session, app_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not app_ids:
        return {}
    stmt = (
        select(Alert.application_id, func.count())
        .where(Alert.application_id.in_(app_ids), Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]))
        .group_by(Alert.application_id)
    )
    return dict(db.execute(stmt).all())  # type: ignore[arg-type]


def application_rows(db: Session, apps: list[FinancialAidApplication]) -> list[ApplicationRow]:
    orgs = org_map(db)
    alerts = open_alert_counts(db, [a.id for a in apps])
    return [
        ApplicationRow(
            id=a.id,
            reference=a.reference,
            organization=OrgRef.model_validate(orgs[a.organization_id]),
            student=student_ref(a.student),
            submitted_at=a.submitted_at,
            award_year=a.award_year,
            status=a.status,
            requested_amount=a.requested_amount,
            verification_status=a.verification_status,
            review_status=a.review_status,
            risk_score=a.risk_score,
            risk_level=a.risk_level,
            last_assessed_at=a.last_assessed_at,
            scenario_key=a.scenario_key,
            open_alerts=alerts.get(a.id, 0),
        )
        for a in apps
    ]


def _in_scope(org_id: uuid.UUID, principal: Principal) -> bool:
    return principal.org_id is None or org_id == principal.org_id


def identity_tokens(db: Session, stu: Student, principal: Principal) -> list[IdentityTokenOut]:
    out = []
    for tok in sorted(stu.identity_tokens, key=lambda t: t.token_type):
        matches = db.execute(
            select(StudentIdentityToken.organization_id).where(
                StudentIdentityToken.token_type == tok.token_type,
                StudentIdentityToken.token_value == tok.token_value,
                StudentIdentityToken.student_id != stu.id,
            )
        ).scalars()
        in_scope = other = 0
        for org_id in matches:
            if _in_scope(org_id, principal):
                in_scope += 1
            else:
                other += 1
        out.append(
            IdentityTokenOut(
                token_type=tok.token_type,
                handle=display_token(tok.token_value),
                shared_in_scope=in_scope,
                shared_other_institutions=other,
            )
        )
    return out


def related_groups(db: Session, app: FinancialAidApplication, principal: Principal) -> list[RelatedGroup]:
    """Other applications linked to this one by a shared identity token, device, network or payment destination."""
    orgs = org_map(db)
    groups: list[tuple[str, str, list[FinancialAidApplication]]] = []

    for tok in app.student.identity_tokens:
        if tok.token_type not in _RELATABLE_TOKENS:
            continue
        others = db.scalars(
            select(FinancialAidApplication)
            .join(StudentIdentityToken, StudentIdentityToken.student_id == FinancialAidApplication.student_id)
            .where(
                StudentIdentityToken.token_type == tok.token_type,
                StudentIdentityToken.token_value == tok.token_value,
                FinancialAidApplication.student_id != app.student_id,
            )
        ).all()
        if others:
            groups.append((tok.token_type, display_token(tok.token_value), list(others)))

    for kind, value in (("device", app.device_token), ("ip", app.ip_token)):
        if not value:
            continue
        column = FinancialAidApplication.device_token if kind == "device" else FinancialAidApplication.ip_token
        others = db.scalars(
            select(FinancialAidApplication).where(column == value, FinancialAidApplication.id != app.id)
        ).all()
        if others:
            groups.append((kind, display_token(value, "DEV" if kind == "device" else "NET"), list(others)))

    dest_ids = db.scalars(
        select(Disbursement.destination_id).where(Disbursement.student_id == app.student_id).distinct()
    ).all()
    for dest_id in dest_ids:
        app_ids = db.scalars(
            select(Disbursement.application_id)
            .where(Disbursement.destination_id == dest_id, Disbursement.student_id != app.student_id)
            .distinct()
        ).all()
        if app_ids:
            dest = db.get(PaymentDestinationToken, dest_id)
            others = db.scalars(select(FinancialAidApplication).where(FinancialAidApplication.id.in_(app_ids))).all()
            groups.append(("destination", display_token(dest.token_value, "DST"), list(others)))  # type: ignore[union-attr]

    result = []
    for kind, handle, others in groups:
        visible = [o for o in others if _in_scope(o.organization_id, principal)]
        result.append(
            RelatedGroup(
                kind=kind,
                label=TOKEN_LABELS[kind],
                handle=handle,
                matches=[
                    RelatedApplication(
                        id=o.id,
                        reference=o.reference,
                        student_ref=o.student.student_ref,
                        organization_name=orgs[o.organization_id].name,
                        risk_level=o.risk_level,
                        risk_score=o.risk_score,
                    )
                    for o in sorted(visible, key=lambda o: o.reference)[:25]
                ],
                other_institution_matches=len(others) - len(visible),
            )
        )
    return sorted(result, key=lambda g: (-(len(g.matches) + g.other_institution_matches), g.kind))


def destination_usage_counts(db: Session, dest_id: uuid.UUID, principal: Principal) -> tuple[int, int]:
    rows = db.execute(
        select(Disbursement.organization_id, Disbursement.student_id)
        .where(Disbursement.destination_id == dest_id)
        .distinct()
    ).all()
    per_scope: dict[bool, set[uuid.UUID]] = defaultdict(set)
    for org_id, student_id in rows:
        per_scope[_in_scope(org_id, principal)].add(student_id)
    return len(per_scope[True]), len(per_scope[False])
