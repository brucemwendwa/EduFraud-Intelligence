"""Payment-provider adapter for student ID-linked financial aid accounts.

Student funds are held by a regulated banking or payment-provider partner, never by the
university or by EduShield. EduShield only *asks* the provider to act (block a card, issue a
replacement, place or lift a restriction, suspend an account) and records the provider's
acknowledgement. There is deliberately no adapter call that reactivates a blocked card or
overrides a provider decision: a blocked card can only be replaced, after identity verification.

`SandboxPaymentProvider` is a deterministic simulation used for demonstrations and tests. It
moves no money, issues no real cards and is labelled "sandbox" in every API response and screen.
A production deployment would implement `PaymentProviderAdapter` for the contracted partner.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

ProviderMode = Literal["sandbox", "live"]


@dataclass(frozen=True)
class ProviderAck:
    """The provider's acknowledgement of a requested control action."""

    reference: str
    status: Literal["accepted", "rejected"]
    message: str
    mode: ProviderMode


@dataclass(frozen=True)
class IssuedCard:
    serial: str  # tokenized immediately by the caller; never persisted in clear
    ack: ProviderAck


class PaymentProviderAdapter(Protocol):
    key: str
    display_name: str
    mode: ProviderMode

    def block_card(self, card_token: str, reason: str) -> ProviderAck: ...

    def issue_replacement(self, card_token: str, account_token: str) -> IssuedCard: ...

    def restrict_account(self, account_token: str, reason: str) -> ProviderAck: ...

    def lift_restriction(self, account_token: str, reason: str) -> ProviderAck: ...

    def suspend_account(self, account_token: str, reason: str) -> ProviderAck: ...

    def reactivate_account(self, account_token: str, reason: str) -> ProviderAck: ...


class SandboxPaymentProvider:
    key = "edushield-sandbox-bank"
    display_name = "Sandbox payment provider (simulated)"
    mode: ProviderMode = "sandbox"

    @staticmethod
    def _ref(kind: str, *parts: str) -> str:
        digest = hashlib.sha256("|".join((kind, *parts)).encode()).hexdigest()[:8].upper()
        return f"SBX-{kind}-{digest}"

    def _ack(self, kind: str, *parts: str, message: str) -> ProviderAck:
        return ProviderAck(self._ref(kind, *parts), "accepted", f"[Sandbox] {message}", self.mode)

    def block_card(self, card_token: str, reason: str) -> ProviderAck:
        return self._ack("BLK", card_token, message="Card blocked. Further authorisations will be declined.")

    def issue_replacement(self, card_token: str, account_token: str) -> IssuedCard:
        serial = f"SBX-CARD-{hashlib.sha256(f'replacement|{card_token}'.encode()).hexdigest()[:12].upper()}"
        ack = self._ack("RPL", card_token, account_token, message="Replacement card issued to the same account.")
        return IssuedCard(serial=serial, ack=ack)

    def restrict_account(self, account_token: str, reason: str) -> ProviderAck:
        return self._ack(
            "RST", account_token, reason, message="Sensitive changes held; everyday card spending continues."
        )

    def lift_restriction(self, account_token: str, reason: str) -> ProviderAck:
        return self._ack("LFT", account_token, reason, message="Restriction lifted.")

    def suspend_account(self, account_token: str, reason: str) -> ProviderAck:
        return self._ack("SUS", account_token, reason, message="Account suspended by the provider on request.")

    def reactivate_account(self, account_token: str, reason: str) -> ProviderAck:
        return self._ack("REA", account_token, reason, message="Account reactivated by the provider.")

    def balance(self, allocated: Decimal, spent: Decimal) -> Decimal:
        """Sandbox balance report: what a provider would return from its ledger."""
        return max(allocated - spent, Decimal("0.00"))


_provider = SandboxPaymentProvider()


def get_payment_provider() -> SandboxPaymentProvider:
    return _provider
