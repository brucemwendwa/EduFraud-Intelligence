"""Infrastructure health for the operations dashboard.

Results describe service state only. Hostnames, keys and provider error text are never returned.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.biometrics.simulated import get_provider
from app.core.config import Settings, get_settings
from app.integrations.payment_provider import get_payment_provider
from app.schemas.common import Schema
from app.services.document_scanner import get_clamav_scanner
from app.services.object_storage import S3ObjectStorage

HealthStatus = Literal["ok", "degraded", "down", "not_configured", "simulated"]
_BACKEND_DIR = Path(__file__).resolve().parents[2]


class ServiceHealth(Schema):
    key: str
    name: str
    status: HealthStatus
    detail: str


def _database(db: Session) -> ServiceHealth:
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - reported as a state; details stay in server logs
        return ServiceHealth(key="database", name="Database", status="down", detail="The database did not respond.")
    return ServiceHealth(key="database", name="Database", status="ok", detail="Responding to queries.")


def _migrations(db: Session) -> ServiceHealth:
    name = "Database migrations"
    try:
        cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
        head = ScriptDirectory.from_config(cfg).get_current_head()
        current = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # noqa: BLE001 - reported as a state; details stay in server logs
        return ServiceHealth(key="migrations", name=name, status="degraded", detail="Migration state is unavailable.")
    if current == head:
        return ServiceHealth(key="migrations", name=name, status="ok", detail=f"At the latest revision ({head}).")
    return ServiceHealth(
        key="migrations", name=name, status="degraded", detail=f"Pending: at {current}, code is {head}."
    )


def _jobs(settings: Settings) -> ServiceHealth:
    name = "Background jobs"
    if settings.jobs_backend == "inline":
        return ServiceHealth(
            key="jobs",
            name=name,
            status="not_configured",
            detail="No queue configured. Jobs run inside the API process and do not survive a restart.",
        )
    try:
        from app.workers.celery_app import celery_app

        with celery_app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=1, timeout=2)
        workers = celery_app.control.ping(timeout=1.0)
    except Exception:  # noqa: BLE001 - reported as a state; details stay in server logs
        return ServiceHealth(key="jobs", name=name, status="down", detail="The job queue is unreachable.")
    if not workers:
        return ServiceHealth(key="jobs", name=name, status="degraded", detail="Queue reachable, but no worker replied.")
    return ServiceHealth(
        key="jobs", name=name, status="ok", detail=f"Queue reachable; {len(workers)} worker(s) replied."
    )


def _storage(settings: Settings) -> ServiceHealth:
    name = "Evidence storage"
    if not settings.s3_bucket_name or not settings.s3_access_key_id or not settings.s3_secret_access_key:
        return ServiceHealth(
            key="storage",
            name=name,
            status="not_configured",
            detail="No private bucket configured. Uploads are refused.",
        )
    try:
        health = S3ObjectStorage(settings).health()
    except Exception:  # noqa: BLE001 - reported as a state; details stay in server logs
        return ServiceHealth(key="storage", name=name, status="down", detail="The storage client could not start.")
    if not health.reachable:
        return ServiceHealth(key="storage", name=name, status="down", detail="The configured bucket is unreachable.")
    gaps = []
    if health.versioning != "Enabled":
        gaps.append(f"versioning {health.versioning or 'unknown'}")
    if health.public_access_blocked is False:
        gaps.append("public access not fully blocked")
    if health.default_encryption is False:
        gaps.append("default encryption off")
    if gaps:
        return ServiceHealth(key="storage", name=name, status="degraded", detail=f"Reachable; {', '.join(gaps)}.")
    return ServiceHealth(key="storage", name=name, status="ok", detail="Bucket reachable; versioning enabled.")


def _scanner(settings: Settings) -> ServiceHealth:
    name = "Malware scanner"
    scanner = get_clamav_scanner(settings)
    if scanner is None:
        return ServiceHealth(
            key="scanner",
            name=name,
            status="not_configured",
            detail="No scanner configured. Uploaded evidence stays quarantined and cannot be downloaded or reviewed.",
        )
    if scanner.ping():
        return ServiceHealth(key="scanner", name=name, status="ok", detail="ClamAV responded.")
    return ServiceHealth(key="scanner", name=name, status="down", detail="ClamAV did not respond.")


def _email(settings: Settings) -> ServiceHealth:
    name = "Email delivery"
    if settings.email_provider != "smtp":
        return ServiceHealth(
            key="email", name=name, status="not_configured", detail="Development mode. No email is sent."
        )
    return ServiceHealth(key="email", name=name, status="ok", detail="SMTP configured; delivery is not probed.")


def service_health(db: Session) -> list[ServiceHealth]:
    settings = get_settings()
    biometric = get_provider()
    payment = get_payment_provider()
    return [
        _database(db),
        _migrations(db),
        _jobs(settings),
        _storage(settings),
        _scanner(settings),
        _email(settings),
        ServiceHealth(
            key="identity",
            name="Identity verification",
            status="simulated",
            detail=f"{biometric.name}: deterministic simulation, no real biometric checks.",
        ),
        ServiceHealth(
            key="payments",
            name="Payment provider",
            status="simulated",
            detail=f"{payment.display_name}: sandbox adapter, no real accounts or funds.",
        ),
    ]


def overall_status(checks: list[ServiceHealth]) -> Literal["ok", "degraded", "down"]:
    """Not-configured and simulated services are limitations, shown separately, not outages."""
    states = {check.status for check in checks}
    if "down" in states:
        return "down"
    return "degraded" if "degraded" in states else "ok"
