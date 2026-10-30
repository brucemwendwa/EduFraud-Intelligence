"""API views for student ID-linked accounts: masking, token handles, location gating and batching."""

from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal
from app.core.permissions import P
from app.core.tokenization import display_token
from app.models import (
    Alert,
    Device,
    Disbursement,
    FinancialAidApplication,
    IdentityVerification,
    InvestigationCase,
    PaymentDestinationToken,
    RiskAssessment,
    SecurityEvent,
    StudentFinancialAccount,
    StudentIDCard,
    Transaction,
    User,
    VerificationRequest,
)
from app.models.enums import DisbursementStatus
from app.schemas.accounts import (
    AccountDetail,
    AccountRow,
    CardOut,
    CardSummary,
    DeviceOut,
    IndicatorOut,
    MethodOption,
    SecurityEventRow,
    TransactionRow,
    VerificationEventOut,
    VerificationRequestDetail,
    VerificationRequestRow,
)
from app.schemas.aid import VerificationRow
from app.schemas.common import OrgRef, UserRef
from app.schemas.risk import AssessmentHistoryItem, RiskAssessmentOut
from app.services import records, risk_views
from app.services.verification_requests import METHOD_LABELS, METHODS, embassy_arrangement


def location(principal: Principal, city: str | None, country: str | None) -> tuple[str | None, bool]:
    """Coarse location for users allowed to see it; everyone else only learns it exists."""
    if not city and not country:
        return None, False
    if not principal.can(P.LOCATION_READ):
        return None, True
    return ", ".join(p for p in (city, country) if p), False


def masked(card: StudentIDCard) -> str:
    return f"•••• {card.display_suffix}"


def card_summary(card: StudentIDCard | None) -> CardSummary | None:
    if card is None:
        return None
    return CardSummary(id=card.id, reference=card.reference, masked_number=masked(card), status=card.status)


def _refs(db: Session, model: type, ids: set[Any]) -> dict[uuid.UUID, str]:
    return risk_views._refs(db, model, ids)  # noqa: SLF001 - shared helper


def _indicators(raw: list[Any]) -> list[IndicatorOut]:
    return [IndicatorOut(**{k: i.get(k) for k in ("code", "title", "category", "points", "description")}) for i in raw]


def _dest(db: Session, dest_id: uuid.UUID | None) -> Any:
    if dest_id is None:
        return None
    dest = db.get(PaymentDestinationToken, dest_id)
    return records.destination_out(dest) if dest else None


# ---------------------------------------------------------------- accounts


def _latest_requests(db: Session, student_ids: set[uuid.UUID]) -> dict[uuid.UUID, VerificationRequest]:
    out: dict[uuid.UUID, VerificationRequest] = {}
    if not student_ids:
        return out
    for req in db.scalars(
        select(VerificationRequest)
        .where(VerificationRequest.student_id.in_(student_ids))
        .order_by(VerificationRequest.created_at)
    ):
        out[req.student_id] = req
    return out


def account_rows(db: Session, accounts: list[StudentFinancialAccount]) -> list[AccountRow]:
    orgs = records.org_map(db)
    ids = [a.id for a in accounts]
    students = {a.student_id for a in accounts}
    allocated = dict(
        db.execute(
            select(Disbursement.account_id, func.sum(Disbursement.amount))
            .where(Disbursement.account_id.in_(ids), Disbursement.status != DisbursementStatus.REVERSED)
            .group_by(Disbursement.account_id)
        ).all()
    )
    cards: dict[uuid.UUID, StudentIDCard] = {}
    for card in db.scalars(
        select(StudentIDCard).where(StudentIDCard.account_id.in_(ids)).order_by(StudentIDCard.issued_at)
    ):
        cards[card.account_id] = card  # type: ignore[index]  # newest card wins
    programs = dict(
        db.execute(
            select(FinancialAidApplication.student_id, FinancialAidApplication.program).where(
                FinancialAidApplication.student_id.in_(students)
            )
        ).all()
    )
    latest = _latest_requests(db, students)
    return [
        AccountRow(
            id=a.id,
            reference=a.reference,
            organization=OrgRef.model_validate(orgs[a.organization_id]),
            student=records.student_ref(a.student),
            department=programs.get(a.student_id),
            status=a.status,
            sensitive_actions_restricted=a.sensitive_actions_restricted,
            study_mode=a.study_mode,
            provider_mode=a.provider_mode,
            card=card_summary(cards.get(a.id)),
            allocated_total=allocated.get(a.id) or Decimal("0"),
            available_balance=a.available_balance,
            balance_as_of=a.balance_as_of,
            last_transaction_at=a.last_transaction_at,
            verification_status=latest[a.student_id].status if a.student_id in latest else "not_required",
            risk_score=a.risk_score,
            risk_level=a.risk_level,
            scenario_key=a.scenario_key,
        )
        for a in accounts
    ]


def card_rows(db: Session, cards: list[StudentIDCard]) -> list[CardOut]:
    from app.services.cards import verified_since_report

    orgs = records.org_map(db)
    accounts = _refs(db, StudentFinancialAccount, {c.account_id for c in cards})
    replaced = _refs(db, StudentIDCard, {c.replaced_by_id for c in cards})
    return [
        CardOut(
            id=c.id,
            reference=c.reference,
            masked_number=masked(c),
            status=c.status,
            organization=OrgRef.model_validate(orgs[c.organization_id]),
            student=records.student_ref(c.student),
            account_id=c.account_id,
            account_ref=accounts.get(c.account_id),  # type: ignore[arg-type]
            issued_at=c.issued_at,
            activated_at=c.activated_at,
            expires_on=c.expires_on,
            reported_lost_at=c.reported_lost_at,
            report_channel=c.report_channel,
            blocked_at=c.blocked_at,
            block_confirmation=c.block_confirmation,
            replacement_requested_at=c.replacement_requested_at,
            replaced_by_id=c.replaced_by_id,
            replaced_by_ref=replaced.get(c.replaced_by_id),  # type: ignore[arg-type]
            verified_since_report=bool(c.reported_lost_at and verified_since_report(db, c)),
        )
        for c in cards
    ]


def device_rows(db: Session, principal: Principal, devices: list[Device]) -> list[DeviceOut]:
    tokens = {d.device_token for d in devices}
    reach: dict[str, list[tuple[uuid.UUID, uuid.UUID]]] = defaultdict(list)
    if tokens:
        for token, student_id, org_id in db.execute(
            select(Device.device_token, Device.student_id, Device.organization_id).where(
                Device.device_token.in_(tokens), Device.is_shared_kiosk.is_(False)
            )
        ):
            reach[token].append((student_id, org_id))
    out = []
    for d in devices:
        others = [(s, o) for s, o in reach[d.device_token] if s != d.student_id]
        in_scope = sum(1 for _, o in others if principal.org_id is None or o == principal.org_id)
        out.append(
            DeviceOut(
                id=d.id,
                handle=display_token(d.device_token, "DEV"),
                label=d.label,
                platform=d.platform,
                trust_status=d.trust_status,
                trust_reason=d.trust_reason,
                first_seen_at=d.first_seen_at,
                last_seen_at=d.last_seen_at,
                is_shared_kiosk=d.is_shared_kiosk,
                student=records.student_ref(d.student),
                other_accounts_in_scope=in_scope,
                other_accounts_other_institutions=len(others) - in_scope,
            )
        )
    return out


def transaction_rows(db: Session, principal: Principal, txns: list[Transaction]) -> list[TransactionRow]:
    orgs = records.org_map(db)
    accounts = _refs(db, StudentFinancialAccount, {t.account_id for t in txns})
    cards = _refs(db, StudentIDCard, {t.card_id for t in txns})
    out = []
    for t in txns:
        loc, restricted = location(principal, t.location_city, t.location_country)
        out.append(
            TransactionRow(
                id=t.id,
                reference=t.reference,
                organization=OrgRef.model_validate(orgs[t.organization_id]),
                student=records.student_ref(t.student),
                account_id=t.account_id,
                account_ref=accounts.get(t.account_id, ""),
                card_ref=cards.get(t.card_id),  # type: ignore[arg-type]
                transaction_type=t.transaction_type,
                channel=t.channel,
                merchant_name=t.merchant_name,
                merchant_category=t.merchant_category,
                amount=t.amount,
                currency=t.currency,
                occurred_at=t.occurred_at,
                location=loc,
                location_restricted=restricted,
                destination=_dest(db, t.destination_id),
                status=t.status,
                decline_reason=t.decline_reason,
                risk_score=t.risk_score,
                risk_level=t.risk_level,
                indicators=_indicators(t.risk_indicators or []),
                review_status=t.review_status,
                scenario_key=t.scenario_key,
            )
        )
    return out


def security_event_rows(db: Session, principal: Principal, events: list[SecurityEvent]) -> list[SecurityEventRow]:
    orgs = records.org_map(db)
    accounts = _refs(db, StudentFinancialAccount, {e.account_id for e in events})
    cards = _refs(db, StudentIDCard, {e.card_id for e in events})
    devices = {d.id: d for d in device_rows(db, principal, [e.device for e in events if e.device is not None])}
    out = []
    for e in events:
        loc, restricted = location(principal, e.location_city, e.location_country)
        out.append(
            SecurityEventRow(
                id=e.id,
                reference=e.reference,
                organization=OrgRef.model_validate(orgs[e.organization_id]),
                student=records.student_ref(e.student),
                account_id=e.account_id,
                account_ref=accounts.get(e.account_id),  # type: ignore[arg-type]
                card_ref=cards.get(e.card_id),  # type: ignore[arg-type]
                event_type=e.event_type,
                source=e.source,
                outcome=e.outcome,
                decision=(e.details or {}).get("decision"),
                occurred_at=e.occurred_at,
                device=devices.get(e.device_id) if e.device_id else None,  # type: ignore[arg-type]
                location=loc,
                location_restricted=restricted,
                destination=_dest(db, e.destination_id),
                risk_score=e.risk_score,
                risk_level=e.risk_level,
                indicators=_indicators(e.risk_indicators or []),
                note=e.note,
                scenario_key=e.scenario_key,
            )
        )
    return out


def verification_request_rows(db: Session, reqs: list[VerificationRequest]) -> list[VerificationRequestRow]:
    orgs = records.org_map(db)
    accounts = _refs(db, StudentFinancialAccount, {r.account_id for r in reqs})
    cards = _refs(db, StudentIDCard, {r.card_id for r in reqs})
    alerts = _refs(db, Alert, {r.alert_id for r in reqs})
    cases = _refs(db, InvestigationCase, {r.case_id for r in reqs})
    return [
        VerificationRequestRow(
            id=r.id,
            reference=r.reference,
            organization=OrgRef.model_validate(orgs[r.organization_id]),
            student=records.student_ref(r.student),
            account_id=r.account_id,
            account_ref=accounts.get(r.account_id),  # type: ignore[arg-type]
            card_ref=cards.get(r.card_id),  # type: ignore[arg-type]
            alert_id=r.alert_id,
            alert_ref=alerts.get(r.alert_id),  # type: ignore[arg-type]
            case_id=r.case_id,
            case_ref=cases.get(r.case_id),  # type: ignore[arg-type]
            trigger=r.trigger,
            reason=r.reason,
            pathway=r.pathway,
            method=r.method,
            status=r.status,
            assigned_to=UserRef.model_validate(r.assigned_to) if r.assigned_to else None,
            notified_at=r.notified_at,
            due_at=r.due_at,
            appointment_at=r.appointment_at,
            location_note=r.location_note,
            decided_at=r.decided_at,
            access_restored=r.access_restored,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reqs
    ]


def verification_request_detail(db: Session, req: VerificationRequest) -> VerificationRequestDetail:
    row = verification_request_rows(db, [req])[0]
    account = db.get(StudentFinancialAccount, req.account_id) if req.account_id else None
    arrangement = embassy_arrangement(db, req, account)
    consent = req.student.biometric_consent
    methods = []
    for pathway, options in METHODS.items():
        for method in options:
            available, reason = True, None
            if method == "embassy_assisted" and arrangement is None:
                available, reason = False, "No formal embassy/consulate arrangement on file for this student."
            elif method == "liveness_provider" and not consent:
                available, reason = False, "Student has not consented to biometric checks."
            methods.append(
                MethodOption(
                    method=method, label=METHOD_LABELS[method], pathway=pathway, available=available, reason=reason
                )
            )
    decider = db.get(User, req.decided_by_id) if req.decided_by_id else None
    attempt = db.get(IdentityVerification, req.identity_verification_id) if req.identity_verification_id else None
    return VerificationRequestDetail(
        **row.model_dump(),
        outcome_reason=req.outcome_reason,
        decided_by=decider.full_name if decider else None,
        biometric_consent=consent,
        study_mode=account.study_mode if account else None,
        embassy_arrangement=arrangement,
        methods=methods,
        identity_verification_ref=attempt.reference if attempt else None,
        events=[VerificationEventOut.model_validate(e) for e in req.events],
    )


def account_detail(db: Session, principal: Principal, account: StudentFinancialAccount) -> AccountDetail:
    row = account_rows(db, [account])[0]
    cards = list(
        db.scalars(
            select(StudentIDCard)
            .where(StudentIDCard.student_id == account.student_id)
            .order_by(StudentIDCard.issued_at.desc())
        )
    )
    devices = list(db.scalars(select(Device).where(Device.student_id == account.student_id)))
    allocations = list(
        db.scalars(
            select(Disbursement).where(Disbursement.account_id == account.id).order_by(Disbursement.disbursed_at.desc())
        )
    )
    txns = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.account_id == account.id)
            .order_by(Transaction.occurred_at.desc())
            .limit(60)
        )
    )
    events = list(
        db.scalars(
            select(SecurityEvent)
            .where(SecurityEvent.student_id == account.student_id)
            .order_by(SecurityEvent.occurred_at.desc())
            .limit(60)
        )
    )
    current = db.scalar(
        select(RiskAssessment).where(RiskAssessment.account_id == account.id, RiskAssessment.is_current)
    )
    history = db.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.account_id == account.id)
        .order_by(RiskAssessment.created_at.desc())
        .limit(20)
    ).all()
    requests = list(
        db.scalars(
            select(VerificationRequest)
            .where(VerificationRequest.student_id == account.student_id)
            .order_by(VerificationRequest.created_at.desc())
        )
    )
    attempts = db.scalars(
        select(IdentityVerification)
        .where(IdentityVerification.student_id == account.student_id)
        .order_by(IdentityVerification.created_at.desc())
    ).all()
    alerts = list(
        db.scalars(select(Alert).where(Alert.student_id == account.student_id).order_by(Alert.created_at.desc()))
    )
    app_ids = [
        a
        for a in db.scalars(
            select(FinancialAidApplication.id).where(FinancialAidApplication.student_id == account.student_id)
        )
    ]
    case_ids = {a.case_id for a in alerts if a.case_id}
    cases = db.scalars(
        select(InvestigationCase).where(
            (InvestigationCase.id.in_(case_ids)) | (InvestigationCase.application_id.in_(app_ids))
        )
    ).all()
    loc, restricted = location(principal, account.home_city, account.home_country)
    return AccountDetail(
        **row.model_dump(),
        provider_key=account.provider_key,
        provider_account_handle=display_token(account.provider_account_token, "ACC"),
        status_reason=account.status_reason,
        restriction_reason=account.restriction_reason,
        restricted_at=account.restricted_at,
        registered_location=loc,
        location_restricted=restricted,
        opened_at=account.opened_at,
        currency=account.currency,
        cards=card_rows(db, cards),
        devices=device_rows(db, principal, devices),
        allocations=records.disbursement_rows(db, allocations),
        transactions=transaction_rows(db, principal, txns),
        security_events=security_event_rows(db, principal, events),
        assessment=RiskAssessmentOut.model_validate(current) if current else None,
        assessment_history=[AssessmentHistoryItem.model_validate(h) for h in history],
        verification_requests=verification_request_rows(db, requests),
        verification_attempts=[VerificationRow.model_validate(v) for v in attempts],
        alerts=risk_views.alert_rows(db, alerts),
        cases=[{"id": str(c.id), "reference": c.reference, "title": c.title, "status": c.status} for c in cases],
    )
