"""Field-level encryption (Fernet: AES-128-CBC + HMAC-SHA256) for revealable PII such as names."""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger("edushield.crypto")


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.data_encryption_key is not None:
        return Fernet(settings.data_encryption_key.get_secret_value().encode())
    # Development fallback only (production refuses to start without DATA_ENCRYPTION_KEY).
    logger.warning("data_encryption_key_not_set_using_derived_development_key")
    derived = hashlib.sha256(b"edushield-dev-fernet:" + settings.tokenization_key.get_secret_value().encode())
    return Fernet(base64.urlsafe_b64encode(derived.digest()))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt field: wrong key or tampered value") from exc
