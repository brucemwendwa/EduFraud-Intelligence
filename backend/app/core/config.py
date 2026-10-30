"""Application settings, loaded from environment variables (and `backend/.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "change-me-jwt-secret-for-local-development-only"  # noqa: S105 - rejected in production
_DEV_TOKENIZATION_KEY = "change-me-tokenization-key-for-local-development"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EduShield AI"
    app_version: str = "0.1.0"
    env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True

    database_url: str = "sqlite:///./var/edushield.db"
    celery_broker_url: str | None = None

    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=60, ge=5, le=24 * 60)
    session_cookie_name: str = "edushield_session"

    tokenization_key: SecretStr = SecretStr(_DEV_TOKENIZATION_KEY)
    data_encryption_key: SecretStr | None = None

    cors_origins: str = "http://localhost:5173"
    login_max_attempts: int = 5
    lockout_minutes: int = 15

    @field_validator("celery_broker_url", "data_encryption_key", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _require_real_secrets_in_production(self) -> Settings:
        if self.env == "production":
            if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set to a unique value in production")
            if self.tokenization_key.get_secret_value() == _DEV_TOKENIZATION_KEY:
                raise ValueError("TOKENIZATION_KEY must be set to a unique value in production")
            if self.data_encryption_key is None:
                raise ValueError("DATA_ENCRYPTION_KEY is required in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production deployments must use PostgreSQL")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def jobs_backend(self) -> Literal["celery", "inline"]:
        return "celery" if self.celery_broker_url else "inline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
