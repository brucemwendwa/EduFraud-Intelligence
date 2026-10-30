"""System settings view: risk configuration, integrations and privacy controls (read-only)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import DB, Principal, require
from app.biometrics.simulated import get_provider
from app.core.config import get_settings
from app.core.permissions import P
from app.detection.account_rules import ACCOUNT_ENGINE_METHOD, ACCOUNT_RULES_VERSION, rule_catalogue
from app.detection.signals import LEVEL_THRESHOLDS
from app.integrations.payment_provider import get_payment_provider
from app.models import Organization
from app.schemas.common import Schema
from app.services.verification_requests import EMBASSY_ARRANGEMENTS, OFFICES

router = APIRouter(prefix="/system", tags=["system"])


class SystemSettings(Schema):
    environment: str
    demo_mode: bool
    risk_bands: list[dict[str, Any]]
    risk_bands_note: str
    account_rules_version: str
    account_engine_method: str
    account_rules: list[dict[str, Any]]
    weights_overridden: bool
    integrations: list[dict[str, Any]]
    verification: list[dict[str, Any]]
    privacy_controls: list[str]


@router.get("/settings", response_model=SystemSettings, summary="Risk configuration, integrations and privacy controls")
def settings_view(db: DB, principal: Annotated[Principal, Depends(require(P.DASHBOARD_READ))]) -> SystemSettings:
    settings = get_settings()
    bands, upper = [], 100.0
    for threshold, level in LEVEL_THRESHOLDS:
        bands.append({"level": level.value, "min": threshold, "max": upper})
        upper = threshold - 0.1
    bands.append({"level": "low", "min": 0.0, "max": upper})
    orgs = [o for o in db.query(Organization).all() if principal.org_id is None or o.id == principal.org_id]
    payment = get_payment_provider()
    biometric = get_provider()
    return SystemSettings(
        environment=settings.env,
        demo_mode=settings.demo_mode,
        risk_bands=list(reversed(bands)),
        risk_bands_note=(
            "Initial demonstration thresholds tuned on synthetic data — not validated production thresholds."
        ),
        account_rules_version=ACCOUNT_RULES_VERSION,
        account_engine_method=ACCOUNT_ENGINE_METHOD,
        account_rules=[
            {
                "code": r.code,
                "category": r.category,
                "severity": r.severity,
                "weight": r.weight,
                "title": r.title,
                "description": r.description,
                "context_only": r.context_only,
            }
            for r in rule_catalogue().values()
        ],
        weights_overridden=bool(settings.account_risk_weights),
        integrations=[
            {
                "name": payment.display_name,
                "kind": "Payment provider (card & account controls)",
                "mode": payment.mode,
                "status": "Simulated adapter — no real accounts, cards or funds",
            },
            {
                "name": "Provider event webhooks",
                "kind": "Transaction and security events (HMAC-signed)",
                "mode": "sandbox",
                "status": "Implemented; fed by the sandbox and the scenario simulator",
            },
            {
                "name": biometric.name,
                "kind": "Identity verification / liveness",
                "mode": biometric.mode,
                "status": "Deterministic simulation — no camera, images or biometric templates",
            },
            {
                "name": "Student information system",
                "kind": "Enrolment and student records",
                "mode": "not connected",
                "status": "Synthetic records only",
            },
        ],
        verification=[
            {
                "institution": o.name,
                "office": OFFICES.get(o.slug),
                "embassy_arrangements": EMBASSY_ARRANGEMENTS.get(o.slug, {}),
            }
            for o in orgs
        ],
        privacy_controls=[
            "Role-based permissions enforced on every API endpoint; institution-level tenant isolation.",
            "Student names encrypted at rest and masked by default; reveals require a reason and are audited.",
            "Card, provider-account, device, session, IP, merchant and payout identifiers stored only as keyed hashes.",
            "No card numbers, PINs, account numbers or biometric templates are stored.",
            "Location: city/country from authorised transaction and sign-in events only — no continuous tracking; "
            "visible only with the location:read permission.",
            "Append-only, hash-chained audit trail protected by database triggers.",
            "Risk scores are decision support: automatic safeguards only hold sensitive changes; people decide.",
        ],
    )
