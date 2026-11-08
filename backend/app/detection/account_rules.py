"""Configurable rule catalogue for the account-protection risk engine.

Every rule has a default weight (0-1: the strength of that evidence on its own), a risk
category and a severity. Weights can be overridden without code changes through the
ACCOUNT_RISK_WEIGHTS setting (a JSON object of code -> weight; 0 disables a rule).

The defaults and the score bands (0-29 low, 30-59 medium, 60-79 high, 80-100 critical) are
initial demonstration values tuned on synthetic data. They are not validated production
thresholds and must be calibrated on real, consented data before any production use.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from functools import lru_cache

from app.core.config import get_settings
from app.models.enums import Severity, SignalCategory

ACCOUNT_RULES_VERSION = "account-rules-2026.10.1"
ACCOUNT_ENGINE_METHOD = "explainable rules over provider events + relationship analysis"

logger = logging.getLogger("edushield.detection")


@dataclass(frozen=True)
class AccountRule:
    code: str
    category: SignalCategory
    severity: Severity
    weight: float
    title: str
    description: str
    context_only: bool = False  # shown for transparency; never escalates on its own


_C = SignalCategory
_S = Severity

DEFAULT_RULES: tuple[AccountRule, ...] = (
    # Identity
    AccountRule(
        "IDV_FAILED_RECENT",
        _C.IDENTITY,
        _S.HIGH,
        0.45,
        "Identity verification failed recently",
        "An identity re-verification for this student failed in the last 30 days.",
    ),
    # Device
    AccountRule(
        "NEW_DEVICE",
        _C.DEVICE,
        _S.LOW,
        0.08,
        "Sign-in from an unfamiliar device",
        "A device not previously confirmed for this student signed in. On its own this is usually a new "
        "phone or laptop.",
    ),
    AccountRule(
        "DEVICE_FLAGGED",
        _C.DEVICE,
        _S.MEDIUM,
        0.30,
        "Device marked suspicious by an officer",
        "An officer marked a device used on this account as suspicious.",
    ),
    # Authentication
    AccountRule(
        "FAILED_LOGIN_BURST",
        _C.AUTHENTICATION,
        _S.MEDIUM,
        0.25,
        "Repeated failed sign-ins",
        "Five or more failed sign-ins within one hour.",
    ),
    AccountRule(
        "MFA_FAILED",
        _C.AUTHENTICATION,
        _S.MEDIUM,
        0.15,
        "Additional authentication failed",
        "A step-up (multi-factor) challenge was failed.",
    ),
    # Account recovery
    AccountRule(
        "PASSWORD_RESET_UNFAMILIAR",
        _C.ACCOUNT_RECOVERY,
        _S.HIGH,
        0.30,
        "Password reset from an unfamiliar session",
        "A password reset or recovery started from a device or session not confirmed for this student.",
    ),
    AccountRule(
        "RECOVERY_REPEATED",
        _C.ACCOUNT_RECOVERY,
        _S.MEDIUM,
        0.20,
        "Repeated account-recovery attempts",
        "Two or more password-reset or recovery requests within seven days.",
    ),
    AccountRule(
        "CONTACT_CHANGE_AFTER_RESET",
        _C.ACCOUNT_RECOVERY,
        _S.HIGH,
        0.25,
        "Contact details changed right after a reset",
        "Recovery email or phone changed within 48 hours of a password reset.",
    ),
    # Financial aid redirection
    AccountRule(
        "AID_REDIRECT_ATTEMPT",
        _C.AID_REDIRECTION,
        _S.HIGH,
        0.40,
        "Attempt to redirect financial aid",
        "A request to move aid or payouts from the ID-linked account to an external destination.",
    ),
    # Transactions
    AccountRule(
        "SPENDING_SPIKE",
        _C.TRANSACTION,
        _S.MEDIUM,
        0.25,
        "Spending far above this student's pattern",
        "A transaction at least four times the student's typical amount (and at least $300).",
    ),
    AccountRule(
        "HIGH_RISK_CATEGORY_NEW",
        _C.TRANSACTION,
        _S.LOW,
        0.12,
        "First use of a high-risk merchant category",
        "First gift-card, crypto-exchange or money-transfer purchase on this account.",
    ),
    AccountRule(
        "RAPID_SEQUENCE",
        _C.TRANSACTION,
        _S.MEDIUM,
        0.30,
        "Burst of transactions",
        "Four or more transactions within 30 minutes, or three high-risk purchases within an hour.",
    ),
    AccountRule(
        "TXN_AFTER_SUSPICIOUS_AUTH",
        _C.TRANSACTION,
        _S.HIGH,
        0.35,
        "Transaction soon after suspicious sign-in activity",
        "A transaction within six hours of a suspicious sign-in, recovery or credential change.",
    ),
    # Location (coarse city/country from authorised events only)
    AccountRule(
        "UNUSUAL_LOCATION",
        _C.LOCATION,
        _S.MEDIUM,
        0.20,
        "Transaction away from the usual locations",
        "A card-present transaction in a place that differs from this student's established pattern.",
    ),
    AccountRule(
        "IMPOSSIBLE_TRAVEL",
        _C.LOCATION,
        _S.HIGH,
        0.40,
        "Physically implausible travel",
        "Card-present transactions in different countries too close together to travel between.",
    ),
    AccountRule(
        "UNUSUAL_LOGIN_LOCATION",
        _C.LOCATION,
        _S.LOW,
        0.12,
        "Sign-in from an unusual country",
        "A sign-in from a country not seen in this student's activity.",
    ),
    AccountRule(
        "NO_LOCAL_ACTIVITY",
        _C.LOCATION,
        _S.INFO,
        0.02,
        "No recent spending near campus (context only)",
        "No card-present spending in the registered campus area for 30+ days. Students travel, study "
        "remotely or save their aid: this is context, never evidence of fraud.",
        context_only=True,
    ),
    # Card security
    AccountRule(
        "CARD_REPORTED_LOST",
        _C.CARD_SECURITY,
        _S.LOW,
        0.10,
        "ID card reported lost or stolen",
        "The student reported their card. This protects them; it is not evidence against them.",
    ),
    AccountRule(
        "TXN_AFTER_CARD_LOST",
        _C.CARD_SECURITY,
        _S.CRITICAL,
        0.60,
        "Card used after it was reported lost",
        "A transaction was attempted with a card after it was reported lost or blocked.",
    ),
    AccountRule(
        "REPLACEMENT_UNVERIFIED",
        _C.CARD_SECURITY,
        _S.LOW,
        0.10,
        "Replacement requested before verification",
        "A replacement card was requested and identity has not yet been re-verified.",
    ),
    # Network / relationships
    AccountRule(
        "DEVICE_SHARED_ACCOUNTS",
        _C.NETWORK,
        _S.HIGH,
        0.35,
        "Device shared across student accounts",
        "One device signed in to three or more different student accounts (registered kiosks excluded).",
    ),
    AccountRule(
        "DESTINATION_SHARED_ACCOUNTS",
        _C.NETWORK,
        _S.HIGH,
        0.45,
        "Destination linked to other students' accounts",
        "Aid redirection or transfers point to a destination already linked to other students.",
    ),
)

# Categories that indicate someone other than the student may control the account.
TAKEOVER_FAMILY = frozenset(
    {
        SignalCategory.AUTHENTICATION,
        SignalCategory.ACCOUNT_RECOVERY,
        SignalCategory.DEVICE,
        SignalCategory.AID_REDIRECTION,
        SignalCategory.IDENTITY,
    }
)
HIGH_RISK_MERCHANT_CATEGORIES = frozenset({"gift_cards", "crypto_exchange", "money_transfer"})


@lru_cache
def rule_catalogue() -> dict[str, AccountRule]:
    """Default rules with any configured weight overrides applied."""
    rules = {r.code: r for r in DEFAULT_RULES}
    raw = get_settings().account_risk_weights
    if raw:
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("ACCOUNT_RISK_WEIGHTS is not valid JSON; using default weights")
            overrides = {}
        for code, weight in overrides.items():
            if code in rules and isinstance(weight, int | float) and 0 <= weight < 1:
                rules[code] = replace(rules[code], weight=float(weight))
            else:
                logger.warning("Ignoring account risk weight override for %s", code)
    return rules


def rule(code: str) -> AccountRule:
    return rule_catalogue()[code]
