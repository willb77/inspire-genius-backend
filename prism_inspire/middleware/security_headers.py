from __future__ import annotations

"""
Security headers middleware and production error handler.

Adds standard security headers to every HTTP response and provides
a catch-all exception handler that prevents stack trace leakage
in production.
"""

import logging
import os
import traceback
from typing import Any
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ── Security headers applied to every response ───────────────────────────

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


# ── Middleware ─────────────────────────────────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects standard security headers into every HTTP response
    and strips the ``Server`` header to reduce fingerprinting.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)

        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        # Remove server identification header
        if "server" in response.headers:
            del response.headers["server"]

        return response


# ── Production error handler ──────────────────────────────────────────────


class ProductionErrorHandler:
    """
    Catch-all exception handler suitable for mounting on a FastAPI app.

    In production (``APP_ENV == "production"``), returns a generic error
    without stack traces.  In other environments the error detail is
    included for easier debugging.

    Usage::

        from prism_inspire.middleware.security_headers import ProductionErrorHandler

        app.add_exception_handler(Exception, ProductionErrorHandler())
    """

    def __call__(self, request: Request, exc: Exception) -> JSONResponse:
        return self.handle(request, exc)

    @staticmethod
    def handle(request: Request, exc: Exception) -> JSONResponse:
        app_env = os.getenv("APP_ENV", "development")

        # Always log the full traceback internally
        logger.error(
            "Unhandled exception on %s %s: %s\n%s",
            request.method,
            request.url.path,
            exc,
            traceback.format_exc(),
        )

        if app_env == "production":
            return JSONResponse(
                status_code=500,
                content={
                    "message": "Internal server error",
                    "status": False,
                    "error_status": {
                        "error_code": "001",
                        "description": "",
                    },
                    "data": {},
                },
            )

        # Development / staging — include error detail
        return JSONResponse(
            status_code=500,
            content={
                "message": "Internal server error",
                "status": False,
                "error_status": {
                    "error_code": "001",
                    "description": str(exc),
                },
                "data": {"traceback": traceback.format_exc()},
            },
        )


# ── CORS origin helper ───────────────────────────────────────────────────


def get_cors_origins() -> list[str]:
    """
    Read and validate CORS origins from the ``ALLOWED_ORIGINS``
    environment variable (comma-separated).

    Logs a warning if a wildcard ``*`` is present.
    """
    from prism_inspire.core.config import settings

    raw = settings.ALLOWED_ORIGINS
    origins: list[str] = []

    for origin in raw.split(","):
        origin = origin.strip()
        if not origin:
            continue

        if origin == "*":
            logger.warning(
                "CORS wildcard '*' detected — this is insecure for production"
            )
            origins.append(origin)
            continue

        parsed = urlparse(origin)
        if parsed.scheme and parsed.netloc:
            origins.append(origin)
        else:
            logger.warning("Ignoring malformed CORS origin: %s", origin)

    return origins
