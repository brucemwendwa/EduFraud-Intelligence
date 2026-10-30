"""Identity rules: duplicate or conflicting identities and reused contact details.

Shared contact details on their own are common (siblings, roommates, residence halls),
so they carry deliberately low weight. Identity conflicts — one SSN token behind
different names or dates of birth — carry high weight.
"""

from __future__ import annotations

from app.detection.context import DetectionContext
from app.detection.signals import Signal
from app.detection.versions import RULES_VERSION
from app.models import FinancialAidApplication
from app.models.enums import Severity, SignalCategory


def evaluate(ctx: DetectionContext, app: FinancialAidApplication) -> list[Signal]:
    signals: list[Signal] = []
    sid, org = app.student_id, app.organization_id
    mine = ctx.student_tokens.get(sid, {})

    ssn_others = ctx.others_with_token(sid, "ssn")
    if ssn_others:
        conflicting = {
            s
            for s in ssn_others
            if ctx.student_tokens.get(s, {}).get("name") != mine.get("name")
            or ctx.student_tokens.get(s, {}).get("dob") != mine.get("dob")
        }
        if conflicting:
            same, other = ctx.split_by_org(conflicting, org)
            signals.append(
                Signal(
                    code="SSN_IDENTITY_CONFLICT",
                    category=SignalCategory.IDENTITY,
                    severity=Severity.HIGH,
                    weight=0.55 if len(conflicting) >= 2 else 0.45,
                    title="SSN token reused with conflicting identity details",
                    description=(
                        f"The same SSN token appears on {len(conflicting)} other student record(s) with a different "
                        "name or date of birth, a pattern consistent with synthetic or stolen identities."
                    ),
                    version=RULES_VERSION,
                    evidence={"records_in_institution": same, "records_at_other_institutions": other},
                )
            )

    phone_others = ctx.others_with_token(sid, "phone")
    email_others = ctx.others_with_token(sid, "email")
    address_others = ctx.others_with_token(sid, "address")
    contact_others = phone_others | email_others
    household = contact_others and contact_others <= address_others
    if contact_others and not household:
        n = len(contact_others)
        signals.append(
            Signal(
                code="CONTACT_REUSE",
                category=SignalCategory.IDENTITY,
                severity=Severity.MEDIUM if n >= 2 else Severity.LOW,
                weight=0.25 if n >= 2 else 0.12,
                title="Phone or email shared with unrelated students",
                description=(
                    f"Contact details are shared with {n} other student(s) who do not live at the same address."
                ),
                version=RULES_VERSION,
                evidence={"students": n, "shared_phone": len(phone_others), "shared_email": len(email_others)},
            )
        )
    elif household or len(address_others) >= 2:
        signals.append(
            Signal(
                code="SHARED_HOUSEHOLD_OR_RESIDENCE",
                category=SignalCategory.IDENTITY,
                severity=Severity.INFO,
                weight=0.04,
                title="Shared address or household contact",
                description=(
                    f"Address shared with {len(address_others)} other student(s). Households and residence halls make "
                    "this common, so it contributes very little on its own."
                ),
                version=RULES_VERSION,
                evidence={"students_at_address": len(address_others)},
            )
        )
    return signals
