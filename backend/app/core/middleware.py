"""HTTP middleware: request IDs, safe access logging, security headers and CSRF defence."""

from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.monitoring import request_metrics

access_log = logging.getLogger("edushield.access")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CLIENT_HEADER = "x-edushield-client"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MULTIPART_OVERHEAD_BYTES = 64 * 1024
# The web client bundle only: Radix and React Flow position elements with inline styles.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID and logs method/path/status/duration — never bodies or query strings."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        # Client-supplied IDs reach logs and response headers, so only simple tokens are accepted.
        request_id = supplied if _SAFE_REQUEST_ID.match(supplied) else uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()
        measured = request.url.path.startswith("/api/v1")
        try:
            response = await call_next(request)
        except Exception:
            if measured:
                request_metrics.record((time.perf_counter() - start) * 1000, 500)
            raise
        if measured:
            request_metrics.record((time.perf_counter() - start) * 1000, response.status_code)
        response.headers["X-Request-ID"] = request_id
        if request.url.path.startswith("/api/") and request.url.path != "/api/health":
            access_log.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Refuses oversized bodies from their declared length, before any multipart parsing or buffering."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        declared = request.headers.get("content-length", "")
        limit = get_settings().document_max_upload_bytes + _MULTIPART_OVERHEAD_BYTES
        if declared.isdigit() and int(declared) > limit:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "payload_too_large", "message": "The request is too large."}},
            )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.path.startswith("/api/v1"):
            headers.setdefault("Cache-Control", "no-store")
        settings = get_settings()
        if settings.frontend_dist and not request.url.path.startswith("/api/"):
            headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        if settings.is_hardened:
            headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Cookie-authenticated unsafe requests must carry the X-EduShield-Client header.

    Browsers cannot attach custom headers to cross-site requests without a CORS
    preflight, which our CORS policy only grants to configured origins. Requests
    using an explicit Bearer token (API clients) are not cookie-borne and are exempt.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method in UNSAFE_METHODS
            and request.url.path.startswith("/api/v1")
            and get_settings().session_cookie_name in request.cookies
            and not request.headers.get("authorization", "").lower().startswith("bearer ")
            and CLIENT_HEADER not in request.headers
        ):
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "csrf_check_failed", "message": "Missing client verification header."}},
            )
        return await call_next(request)
