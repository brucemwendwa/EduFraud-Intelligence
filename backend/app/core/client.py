"""The client address used for per-client limits and audit records."""

from __future__ import annotations

from ipaddress import ip_address

from starlette.requests import Request

from app.core.config import get_settings


def client_address(request: Request) -> str:
    """Forwarded headers are client-supplied unless the platform overwrites them, so only a configured one is read."""
    header = get_settings().client_ip_header
    if header:
        candidate = request.headers.get(header, "").split(",")[0].strip()
        try:
            return str(ip_address(candidate))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"
