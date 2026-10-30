"""HTTP middleware: request IDs, safe access logging, security headers and CSRF defence."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings

access_log = logging.getLogger("edushield.access")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CLIENT_HEADER = "x-edushield-client"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID and logs method/path/status/duration — never bodies or query strings."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
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
        if get_settings().is_production:
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
