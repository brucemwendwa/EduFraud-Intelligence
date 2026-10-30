from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, Principal, get_scoped_or_404, require, scoped
from app.biometrics.provider import ConsentRequiredError
from app.biometrics.simulated import FACE_MATCH_THRESHOLD, FACE_MISMATCH_THRESHOLD, LIVENESS_THRESHOLD, TEST_SAMPLES
from app.core.errors import ConflictError, ValidationFailedError
from app.core.permissions import P
from app.db.types import utcnow
from app.models import FinancialAidApplication, IdentityVerification, Student, User
from app.models.enums import AuditCategory, AuditOutcome, VerificationOutcome, VerificationTrigger
from app.schemas.common import OrgRef, Page, Pagination
from app.schemas.verification import (
    AlternativeVerificationIn,
    BiometricVerificationIn,
    ProviderInfo,
    StageOut,
    TestSampleOut,
    VerificationOut,
    VerificationStats,
)
from app.services import audit, records
from app.services import verification as service

router = APIRouter(prefix="/verifications", tags=["verifications"])

Reader = Annotated[Principal, Depends(require(P.VERIFICATIONS_READ))]
Initiator = Annotated[Principal, Depends(require(P.VERIFICATIONS_INITIATE))]


def _out(db: DB, rows: list[IdentityVerification]) -> list[VerificationOut]:
    orgs = records.org_map(db)
    apps = {
        a.id: a
        for a in db.scalars(
            select(FinancialAidApplication).where(FinancialAidApplication.id.in_({r.application_id for r in rows}))
        )
    }
    users = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_({r.initiated_by_id for r in rows})))}
    out = []
    for v in rows:
        app = apps.get(v.application_id)  # type: ignore[arg-type]
        out.append(
            VerificationOut(
                id=v.id,
                reference=v.reference,
                organization=OrgRef.model_validate(orgs[v.organization_id]),
                student=records.student_ref(v.student),
                application_id=v.application_id,
                application_ref=app.reference if app else None,
                trigger=v.trigger,
                method=v.method,
                provider=v.provider,
                provider_mode=v.provider_mode,
                status=v.status,
                document_result=v.document_result,
                face_match_score=v.face_match_score,
                liveness_score=v.liveness_score,
                liveness_result=v.liveness_result,
                pad_result=v.pad_result,
                pad_attack_type=v.pad_attack_type,
                risk_indicators=list(v.risk_indicators or []),
                recommended_action=v.recommended_action,
                sample_key=v.sample_key,
                stages=[StageOut(**s) for s in (v.session_context or {}).get("stages", [])],
                notes=v.notes,
                initiated_by=users.get(v.initiated_by_id) if v.initiated_by_id else "Student self-service",  # type: ignore[arg-type]
                completed_at=v.completed_at,
                created_at=v.created_at,
                resulting_risk_score=app.risk_score if app else None,
                resulting_risk_level=app.risk_level if app else None,
            )
        )
    return out


@router.get("/provider", response_model=ProviderInfo, summary="Verification provider details (simulation)")
def provider_info(_: Reader) -> ProviderInfo:
    return ProviderInfo(
        name="edushield-simulated-idv",
        mode="simulation",
        disclaimer=(
            "SIMULATED PROVIDER. No real biometric processing takes place and no camera is used. Results are generated "
            "from synthetic test samples to demonstrate the workflow. A production deployment would integrate an "
            "authorized commercial identity-verification vendor through the same provider interface."
        ),
        data_handling=[
            "No face images, document images or biometric templates are stored by EduShield.",
            "Only scores, outcomes and reason codes are recorded.",
            "Biometric checks run only for students who have given explicit consent.",
            "Students who decline are verified in person, by officer video call or by mailed code.",
        ],
        thresholds={
            "face_match": FACE_MATCH_THRESHOLD,
            "face_mismatch": FACE_MISMATCH_THRESHOLD,
            "liveness": LIVENESS_THRESHOLD,
        },
        samples=[
            TestSampleOut(key=s.key, label=s.label, description=s.description, expected=s.expected)
            for s in TEST_SAMPLES.values()
        ],
        triggers=[t.value for t in VerificationTrigger],
        alternative_methods=["in_person_id_check", "officer_video_call", "mailed_code"],
    )


@router.get("", response_model=Page[VerificationOut], summary="Verification history")
def list_verifications(
    db: DB,
    principal: Reader,
    paging: Annotated[Pagination, Depends()],
    status: VerificationOutcome | None = None,
    trigger: VerificationTrigger | None = None,
    method: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=60, description="IDV-, FA- or STU- reference")] = None,
) -> Page[VerificationOut]:
    stmt = scoped(select(IdentityVerification), IdentityVerification, principal)
    if status:
        stmt = stmt.where(IdentityVerification.status == status.value)
    if trigger:
        stmt = stmt.where(IdentityVerification.trigger == trigger.value)
    if method:
        stmt = stmt.where(IdentityVerification.method == method)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = (
            stmt.join(Student, Student.id == IdentityVerification.student_id)
            .outerjoin(FinancialAidApplication, FinancialAidApplication.id == IdentityVerification.application_id)
            .where(
                or_(
                    func.lower(IdentityVerification.reference).like(like),
                    func.lower(Student.student_ref).like(like),
                    func.lower(FinancialAidApplication.reference).like(like),
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(IdentityVerification.created_at.desc()).offset(paging.offset).limit(paging.page_size)
    ).all()
    return Page(items=_out(db, list(rows)), total=total, page=paging.page, page_size=paging.page_size)


@router.get("/stats", response_model=VerificationStats, summary="Verification outcomes for the current scope")
def stats(db: DB, principal: Reader) -> VerificationStats:
    rows = db.execute(
        scoped(
            select(
                IdentityVerification.status,
                IdentityVerification.trigger,
                IdentityVerification.method,
                IdentityVerification.pad_result,
                IdentityVerification.created_at,
            ),
            IdentityVerification,
            principal,
        )
    ).all()
    status = Counter(r.status for r in rows)
    total = len(rows)
    decided = status["passed"] + status["failed"]
    since = utcnow() - timedelta(days=90)
    daily: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        if r.created_at >= since:
            daily[r.created_at.date().isoformat()][r.status] += 1
    return VerificationStats(
        total=total,
        passed=status["passed"],
        failed=status["failed"],
        review=status["review"],
        pass_rate=round(status["passed"] / decided, 3) if decided else None,
        attacks_detected=sum(1 for r in rows if r.pad_result == "attack_detected"),
        biometric_share=round(sum(1 for r in rows if r.method == "document_biometric") / total, 3) if total else None,
        by_trigger=dict(Counter(r.trigger for r in rows)),
        by_method=dict(Counter(r.method for r in rows)),
        daily=[{"date": d, **dict(c)} for d, c in sorted(daily.items())],
    )


@router.get("/{verification_id}", response_model=VerificationOut, summary="Verification detail with stage results")
def get_verification(verification_id: uuid.UUID, db: DB, principal: Reader) -> VerificationOut:
    return _out(db, [get_scoped_or_404(db, IdentityVerification, verification_id, principal, "Verification")])[0]


@router.post(
    "", response_model=VerificationOut, status_code=201, summary="Run a step-up biometric verification (simulated)"
)
def start_biometric(body: BiometricVerificationIn, request: Request, db: DB, principal: Initiator) -> VerificationOut:
    if body.sample_key not in TEST_SAMPLES:
        raise ValidationFailedError(
            "Unknown test sample.", details=[{"field": "sample_key", "message": "Choose one of the synthetic samples"}]
        )
    app = get_scoped_or_404(db, FinancialAidApplication, body.application_id, principal, "Application")
    try:
        v = service.run_biometric(
            db, app=app, trigger=body.trigger.value, sample_key=body.sample_key, user=principal.user, request=request
        )
    except ConsentRequiredError as exc:
        db.rollback()
        audit.record(
            db,
            category=AuditCategory.VERIFICATION,
            action="verification.biometric",
            outcome=AuditOutcome.DENIED,
            actor=principal.user,
            organization_id=app.organization_id,
            target_type="application",
            target_id=app.id,
            target_ref=app.reference,
            details={"reason": "biometric_consent_required", "trigger": body.trigger.value},
            request=request,
        )
        db.commit()
        raise ConflictError(
            "This student has not consented to biometric verification. Use an alternative verification method.",
            code="biometric_consent_required",
        ) from exc
    db.commit()
    return _out(db, [v])[0]


@router.post(
    "/alternative", response_model=VerificationOut, status_code=201, summary="Record an officer-led verification"
)
def record_alternative(
    body: AlternativeVerificationIn, request: Request, db: DB, principal: Initiator
) -> VerificationOut:
    app = get_scoped_or_404(db, FinancialAidApplication, body.application_id, principal, "Application")
    v = service.record_alternative(
        db,
        app=app,
        method=body.method,
        outcome=body.outcome,
        trigger=body.trigger.value,
        notes=body.notes,
        user=principal.user,
        request=request,
    )
    db.commit()
    return _out(db, [v])[0]
