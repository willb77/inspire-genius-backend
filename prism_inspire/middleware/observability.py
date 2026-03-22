"""
Observability middleware: correlation IDs, request logging, and latency tracking.

Adds X-Correlation-ID header to every request/response and emits structured
log lines for each HTTP request with duration, status, and user context.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from prism_inspire.core.log_config import logger, set_correlation_id


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Generates or propagates a correlation ID (X-Correlation-ID header)
    2. Logs every request with method, path, status, duration, and caller info
    3. Tracks latency for monitoring dashboards
    """

    # Paths to exclude from access logging (noisy health checks)
    SKIP_LOG_PATHS = {"/health", "/health/ready", "/health/live", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # ── Correlation ID ────────────────────────────────────────
        incoming_cid = request.headers.get("x-correlation-id")
        cid = set_correlation_id(incoming_cid)

        # ── Timing ────────────────────────────────────────────────
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "Unhandled exception",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "ip": request.client.host if request.client else None,
                },
                exc_info=True,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # ── Add correlation ID to response ────────────────────────
        response.headers["X-Correlation-ID"] = cid

        # ── Access log ────────────────────────────────────────────
        path = request.url.path
        if path not in self.SKIP_LOG_PATHS:
            log_level = "warning" if response.status_code >= 400 else "info"
            getattr(logger, log_level)(
                f"{request.method} {path} {response.status_code} ({duration_ms}ms)",
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent", "")[:200],
                },
            )

        return response
