"""Detection context: one in-memory snapshot of the data every rule needs, with lookup indexes.

The snapshot is platform-wide so that cross-institution patterns (the same SSN token or
payment destination at two schools) can be detected. Rules only ever surface counts for
other institutions — never their records. At prototype scale (hundreds of records) a
snapshot is fast and simple; production would back this with an incremental feature store.
"""

from __future__ import annotations

import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.types import utcnow
from app.models import (
    Disbursement,
    EnrollmentRecord,
    FinancialAidApplication,
    IdentityVerification,
    StudentIdentityToken,
)


@dataclass
class DetectionContext:
    now: datetime
    applications: list[FinancialAidApplication]
    student_tokens: dict[uuid.UUID, dict[str, str]] = field(default_factory=dict)
    token_students: dict[tuple[str, str], set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    student_org: dict[uuid.UUID, uuid.UUID] = field(default_factory=dict)
    device_apps: dict[str, list[FinancialAidApplication]] = field(default_factory=lambda: defaultdict(list))
    ip_apps: dict[str, list[FinancialAidApplication]] = field(default_factory=lambda: defaultdict(list))
    student_apps: dict[uuid.UUID, list[FinancialAidApplication]] = field(default_factory=lambda: defaultdict(list))
    student_disbursements: dict[uuid.UUID, list[Disbursement]] = field(default_factory=lambda: defaultdict(list))
    destination_students: dict[uuid.UUID, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    student_enrollments: dict[uuid.UUID, list[EnrollmentRecord]] = field(default_factory=lambda: defaultdict(list))
    student_verifications: dict[uuid.UUID, list[IdentityVerification]] = field(
        default_factory=lambda: defaultdict(list)
    )
    # Robust amount statistics per fund type: (median, scaled MAD)
    amount_stats: dict[str, tuple[float, float]] = field(default_factory=dict)

    def others_with_token(self, student_id: uuid.UUID, token_type: str) -> set[uuid.UUID]:
        value = self.student_tokens.get(student_id, {}).get(token_type)
        if value is None:
            return set()
        return self.token_students[(token_type, value)] - {student_id}

    def split_by_org(self, student_ids: set[uuid.UUID], org_id: uuid.UUID) -> tuple[int, int]:
        same = sum(1 for s in student_ids if self.student_org.get(s) == org_id)
        return same, len(student_ids) - same


def build_context(db: Session, now: datetime | None = None) -> DetectionContext:
    ctx = DetectionContext(now=now or utcnow(), applications=list(db.scalars(select(FinancialAidApplication))))

    for student_id, org_id, token_type, value in db.execute(
        select(
            StudentIdentityToken.student_id,
            StudentIdentityToken.organization_id,
            StudentIdentityToken.token_type,
            StudentIdentityToken.token_value,
        )
    ):
        ctx.student_tokens.setdefault(student_id, {})[token_type] = value
        ctx.token_students[(token_type, value)].add(student_id)
        ctx.student_org[student_id] = org_id

    for app in ctx.applications:
        ctx.student_apps[app.student_id].append(app)
        if app.device_token:
            ctx.device_apps[app.device_token].append(app)
        if app.ip_token:
            ctx.ip_apps[app.ip_token].append(app)

    amounts: dict[str, list[float]] = defaultdict(list)
    for d in db.scalars(select(Disbursement)):
        ctx.student_disbursements[d.student_id].append(d)
        ctx.destination_students[d.destination_id].add(d.student_id)
        amounts[d.fund_type].append(float(d.amount))
    for fund, values in amounts.items():
        median = statistics.median(values)
        mad = statistics.median(abs(v - median) for v in values) * 1.4826
        ctx.amount_stats[fund] = (median, max(mad, 1.0))

    for e in db.scalars(select(EnrollmentRecord)):
        ctx.student_enrollments[e.student_id].append(e)
    for v in db.scalars(select(IdentityVerification).order_by(IdentityVerification.created_at)):
        ctx.student_verifications[v.student_id].append(v)
    return ctx
