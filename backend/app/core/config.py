"""Application settings, loaded from environment variables (and `backend/.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "change-me-jwt-secret-for-local-development-only"  # noqa: S105 - rejected in production
_DEV_TOKENIZATION_KEY = "change-me-tokenization-key-for-local-development"
_DEV_WEBHOOK_SECRET = "change-me-sandbox-provider-webhook-secret"  # noqa: S105 - rejected in production


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "EduShield AI"
    app_version: str = "0.1.0"
    # "demo" is a hosted synthetic-data environment: hardened like production, but demo sign-in is allowed.
    env: Literal["development", "test", "demo", "production"] = "development"
    # Demo authentication is opt-in. Shared and production deployments must enable it
    # explicitly for an isolated synthetic-data demonstration.
    demo_mode: bool = False

    database_url: str = "sqlite:///./var/edushield.db"
    celery_broker_url: str | None = None

    jwt_secret: SecretStr = SecretStr(_DEV_JWT_SECRET)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=60, ge=5, le=24 * 60)
    session_cookie_name: str = "edushield_session"

    tokenization_key: SecretStr = SecretStr(_DEV_TOKENIZATION_KEY)
    data_encryption_key: SecretStr | None = None

    # Shared secret the payment/identity provider uses to sign event webhooks (HMAC-SHA256).
    provider_webhook_secret: SecretStr = SecretStr(_DEV_WEBHOOK_SECRET)
    # Optional JSON object overriding account-risk rule weights, e.g. {"NEW_DEVICE": 0.05}.
    account_risk_weights: str | None = None

    # Optional error monitoring. Unset means no data leaves the application.
    sentry_dsn: SecretStr | None = None

    cors_origins: str = "http://localhost:5173"
    # A header the hosting platform itself sets to the caller's address. Unset means the socket address is used.
    client_ip_header: str | None = None
    # Set to the built web client's directory to serve it from the API's own origin.
    frontend_dist: str | None = None
    login_max_attempts: int = 5
    lockout_minutes: int = 15
    student_invitation_ttl_hours: int = Field(default=72, ge=1, le=24 * 14)
    student_activation_base_url: str = "http://localhost:5173/activate"
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=240)
    # Defaults to the Redis broker. Set explicitly to keep rate-limit counters on a separate instance.
    rate_limit_redis_url: str | None = None
    # Public address used in notification emails. Defaults to the host of the activation link.
    public_url: str | None = None

    # SMTP is an integration boundary; development deliberately never sends real mail.
    email_provider: Literal["development", "smtp"] = "development"
    email_from: str = "no-reply@edushield.local"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None

    # Private S3-compatible evidence storage. There is deliberately no filesystem fallback.
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket_name: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_use_tls: bool = True
    s3_addressing_style: Literal["auto", "path", "virtual"] = "auto"
    s3_presigned_url_ttl_seconds: int = Field(default=300, ge=30, le=900)
    document_max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    document_scanner_provider: Literal["unconfigured", "clamav"] = "unconfigured"
    clamav_host: str | None = None
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: int = Field(default=60, ge=1, le=600)
    document_scan_max_attempts: int = Field(default=3, ge=1, le=10)
    document_scan_lease_seconds: int = Field(default=15 * 60, ge=60, le=24 * 60 * 60)
    document_scan_retry_base_seconds: int = Field(default=60, ge=10, le=60 * 60)

    @field_validator("database_url", mode="before")
    @classmethod
    def _use_the_installed_postgres_driver(cls, v: object) -> object:
        """Hosting platforms hand out postgres:// or postgresql:// URLs; this application ships psycopg 3."""
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @field_validator(
        "celery_broker_url",
        "data_encryption_key",
        "account_risk_weights",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "s3_endpoint_url",
        "s3_bucket_name",
        "s3_access_key_id",
        "s3_secret_access_key",
        "clamav_host",
        "frontend_dist",
        "public_url",
        "rate_limit_redis_url",
        "sentry_dsn",
        "client_ip_header",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @model_validator(mode="after")
    def _scanner_needs_a_host(self) -> Settings:
        if self.document_scanner_provider == "clamav" and not self.clamav_host:
            raise ValueError("CLAMAV_HOST is required when DOCUMENT_SCANNER_PROVIDER is clamav")
        return self

    @model_validator(mode="after")
    def _require_real_secrets_when_hosted(self) -> Settings:
        if self.env in ("demo", "production"):
            if self.jwt_secret.get_secret_value() == _DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set to a unique value in production")
            if self.tokenization_key.get_secret_value() == _DEV_TOKENIZATION_KEY:
                raise ValueError("TOKENIZATION_KEY must be set to a unique value in production")
            if self.provider_webhook_secret.get_secret_value() == _DEV_WEBHOOK_SECRET:
                raise ValueError("PROVIDER_WEBHOOK_SECRET must be set to a unique value in production")
            if self.data_encryption_key is None:
                raise ValueError("DATA_ENCRYPTION_KEY is required in production")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production deployments must use PostgreSQL")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must list exact origins")
        if self.env == "production":
            if self.demo_mode:
                raise ValueError("DEMO_MODE must be false in production")
            if self.email_provider != "smtp" or not self.smtp_host or not self.smtp_username or not self.smtp_password:
                raise ValueError("Production requires configured SMTP email delivery for student invitations")
            if not self.s3_bucket_name or not self.s3_access_key_id or not self.s3_secret_access_key:
                raise ValueError("Production requires private S3 document storage configuration")
            if not self.s3_use_tls:
                raise ValueError("Production requires TLS for document storage")
            if not self.student_activation_base_url.startswith("https://"):
                raise ValueError("STUDENT_ACTIVATION_BASE_URL must be an https:// address in production")
            if self.public_url and not self.public_url.startswith("https://"):
                raise ValueError("PUBLIC_URL must be an https:// address in production")
            if self.email_from.rstrip("> ").endswith(".local"):
                raise ValueError("EMAIL_FROM must use a verified sending domain in production")
        return self

    @property
    def rate_limit_store_url(self) -> str | None:
        if self.rate_limit_redis_url:
            return self.rate_limit_redis_url
        broker = self.celery_broker_url or ""
        return broker if broker.startswith(("redis://", "rediss://")) else None

    @property
    def public_app_url(self) -> str:
        return (self.public_url or self.student_activation_base_url.removesuffix("/activate")).rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_hardened(self) -> bool:
        """Served over HTTPS to real browsers: secure cookies, HSTS and no public API docs."""
        return self.env in ("demo", "production")

    @property
    def jobs_backend(self) -> Literal["celery", "inline"]:
        return "celery" if self.celery_broker_url else "inline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
