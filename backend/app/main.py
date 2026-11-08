"""EduShield AI API — application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    CSRFMiddleware,
    RequestContextMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.db.session import SessionLocal
from app.services.rbac import sync_rbac

DESCRIPTION = """
Financial aid fraud detection, identity protection and investigation API.

**Decision support only.** Risk scores and alerts are recommendations for human
review; the platform never denies aid or labels a student fraudulent automatically.

All data served by this prototype is **synthetic**. Biometric verification uses a
clearly labelled **simulated provider**. No FSA/FAFSA systems are connected.

Authenticate with `POST /api/v1/auth/login`; the session is an httpOnly cookie.
API clients may instead send `Authorization: Bearer <access_token>`.
"""

TAGS = [
    {"name": "auth", "description": "Sessions and the current user"},
    {"name": "dashboard", "description": "Portfolio metrics, trends and recent security activity"},
    {"name": "student accounts", "description": "Provider-held financial aid accounts accessed with the ID card"},
    {"name": "student id cards", "description": "Card lifecycle: lost reports, provider blocks, replacements"},
    {"name": "transaction intelligence", "description": "Provider transaction events with explainable risk"},
    {"name": "device & access intelligence", "description": "Devices, sign-ins, credential and recovery events"},
    {"name": "identity verification", "description": "Re-verification requests: on-campus and remote pathways"},
    {"name": "provider events (sandbox)", "description": "HMAC-signed webhooks from the sandbox providers"},
    {"name": "scenario simulator (demo)", "description": "Replay synthetic scenarios (demo mode only)"},
    {"name": "applications", "description": "Financial aid application monitoring"},
    {"name": "students", "description": "Masked student identity and audited reveal"},
    {"name": "disbursements", "description": "Disbursement monitoring and holds"},
    {"name": "verifications", "description": "Identity verification (simulated biometric provider)"},
    {"name": "alerts", "description": "Fraud alert triage"},
    {"name": "network", "description": "Fraud relationship graph"},
    {"name": "cases", "description": "Investigation case management"},
    {"name": "cases", "description": "Investigation cases: evidence, notes, assignment, justified human decisions"},
    {"name": "detection", "description": "Detection engine status and runs"},
    {"name": "audit", "description": "Tamper-evident audit trail"},
    {"name": "organizations", "description": "Institutions"},
    {"name": "users", "description": "Users, roles and permissions"},
    {"name": "notifications", "description": "In-app notifications"},
    {"name": "search", "description": "Global search"},
    {"name": "system", "description": "Health, readiness and read-only system settings"},
    {"name": "operations", "description": "Institution-scoped service health, background jobs and processing activity"},
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Keep DB roles/permissions in step with the code-defined catalogue (idempotent).
    try:
        with SessionLocal() as db:
            sync_rbac(db)
            db.commit()
    except Exception:  # noqa: BLE001 - the API still serves health checks if migrations are pending
        logging.getLogger("edushield.startup").exception("rbac_sync_failed_run_migrations_first")
    yield


def mount_web_client(app: FastAPI, directory: str) -> None:
    """Serve the built web client from the API's origin, which the SameSite=Strict session cookie relies on."""
    dist = Path(directory).resolve()
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def web_client(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging("INFO" if settings.env != "test" else "WARNING")

    app = FastAPI(
        title="EduShield AI API",
        version=settings.app_version,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        docs_url=None if settings.is_hardened else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_hardened else "/api/openapi.json",
        lifespan=lifespan,
    )

    # Starlette runs middleware in reverse order of registration: CORS is outermost.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-EduShield-Client", "X-Organization-Id", "X-Request-ID"],
    )
    register_error_handlers(app)

    @app.get("/api/health", tags=["system"], summary="Liveness probe")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "edushield-api", "version": settings.app_version}

    @app.get("/api/ready", tags=["system"], summary="Readiness probe (database reachable)")
    def ready() -> dict[str, str]:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok", "jobs_backend": settings.jobs_backend}

    app.include_router(api_router, prefix="/api/v1")
    if settings.frontend_dist:
        mount_web_client(app, settings.frontend_dist)  # last, so its catch-all never shadows an API route
    return app


app = create_app()
