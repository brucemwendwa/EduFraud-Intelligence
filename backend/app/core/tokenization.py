"""Keyed pseudonymization of identity attributes.

Raw identifiers (SSN, date of birth, email, phone, address, bank account, device id)
are never persisted. They are normalized and run through HMAC-SHA256 with a
platform secret, so the same attribute always yields the same token (enabling
duplicate and cross-institution matching) while the token reveals nothing and cannot
be reversed without the key.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from enum import StrEnum

from app.core.config import get_settings


class TokenType(StrEnum):
    SSN = "ssn"
    DOB = "dob"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    DEVICE = "device"
    IP = "ip"
    BANK_ACCOUNT = "bank_account"
    NAME = "name"


_DIGITS_ONLY = {TokenType.SSN, TokenType.PHONE, TokenType.BANK_ACCOUNT}


def normalize(kind: TokenType, value: str) -> str:
    value = value.strip().lower()
    if kind in _DIGITS_ONLY:
        return re.sub(r"\D", "", value)
    return re.sub(r"\s+", " ", re.sub(r"[^\w@.\s-]", "", value))


def tokenize(kind: TokenType, value: str) -> str:
    key = get_settings().tokenization_key.get_secret_value().encode()
    message = f"{kind.value}:{normalize(kind, value)}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def display_token(token: str, prefix: str = "TKN") -> str:
    """Short, human-friendly handle for a token (safe to show in the UI)."""
    return f"{prefix}-{token[:6].upper()}"


def hash_ip(ip: str | None) -> str | None:
    """Audit logs keep a keyed hash of the client IP, not the address itself."""
    return tokenize(TokenType.IP, ip)[:16] if ip else None
