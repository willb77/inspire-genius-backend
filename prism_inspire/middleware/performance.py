from __future__ import annotations

"""
Performance middleware and resource management utilities.

- CircuitBreaker  — resilience pattern for external service calls
- TimeoutMiddleware — ASGI middleware enforcing per-request timeouts
- MemoryMonitor   — runtime memory usage tracking
- get_optimized_engine_kwargs — SQLAlchemy pool tuning helper
"""

import asyncio
import logging
import time
from typing import Any, Callable

import psutil
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


# ── Circuit Breaker ─────────────────────────────────────────────────────


class CircuitBreaker:
    """
    Tracks failures for an external service and prevents cascading errors.

    States:
    - **closed** — requests flow normally
    - **open** — requests are blocked (raises immediately)
    - **half-open** — one trial request allowed to test recovery
    """

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures: int = 0
        self.state: str = "closed"  # closed | open | half-open
        self.last_failure_time: float | None = None

    def is_open(self) -> bool:
        """Return True if the breaker is open and not yet ready to retry."""
        if self.state == "open":
            if (
                self.last_failure_time is not None
                and (time.time() - self.last_failure_time) >= self.reset_timeout
            ):
                self.state = "half-open"
                return False
            return True
        return False

    def record_failure(self) -> None:
        """Record a failure; open the breaker if threshold is reached."""
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                "Circuit breaker OPEN after %d failures", self.failures
            )

    def record_success(self) -> None:
        """Record a success; reset the breaker to closed."""
        self.failures = 0
        self.state = "closed"
        self.last_failure_time = None

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute *func* through the circuit breaker.

        Raises ``RuntimeError`` if the breaker is open.
        """
        if self.is_open():
            raise RuntimeError("Circuit breaker is open — call rejected")

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


# ── Timeout Middleware ──────────────────────────────────────────────────

# Paths that are allowed a longer timeout (export, report generation)
LONG_TIMEOUT_PATHS: list[str] = [
    "/analytics/export",
    "/reports/generate",
]

DEFAULT_TIMEOUT_S = 30
LONG_TIMEOUT_S = 120


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that enforces request-level timeouts.

    - Default: 30 s
    - Long operations (export, reports): 120 s
    - Returns HTTP 504 on timeout
    """

    def __init__(
        self,
        app: Any,
        default_timeout: float = DEFAULT_TIMEOUT_S,
        long_timeout: float = LONG_TIMEOUT_S,
    ) -> None:
        super().__init__(app)
        self.default_timeout = default_timeout
        self.long_timeout = long_timeout

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        timeout = self.default_timeout
        path = request.url.path
        if any(lp in path for lp in LONG_TIMEOUT_PATHS):
            timeout = self.long_timeout

        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.error(
                "Request timed out: %s %s (timeout=%ds)",
                request.method,
                path,
                timeout,
            )
            return JSONResponse(
                status_code=504,
                content={
                    "status": "error",
                    "message": f"Request timed out after {timeout}s",
                    "error_code": "TIMEOUT",
                },
            )


# ── Memory Monitor ──────────────────────────────────────────────────────


class MemoryMonitor:
    """Monitors process memory usage and logs warnings above a threshold."""

    def __init__(self, threshold_mb: float = 512) -> None:
        self.threshold_mb = threshold_mb

    def check(self) -> dict[str, Any]:
        """Return current memory stats."""
        process = psutil.Process()
        current_mb = process.memory_info().rss / (1024 * 1024)
        return {
            "current_mb": round(current_mb, 2),
            "threshold_mb": self.threshold_mb,
            "ok": current_mb < self.threshold_mb,
        }

    def log_if_high(self) -> None:
        """Log a warning if memory exceeds the threshold."""
        stats = self.check()
        if not stats["ok"]:
            logger.warning(
                "High memory usage: %.1fMB (threshold: %.0fMB)",
                stats["current_mb"],
                stats["threshold_mb"],
            )


# ── Connection pool optimization ────────────────────────────────────────


def get_optimized_engine_kwargs(target_concurrent: int = 500) -> dict[str, Any]:
    """
    Return SQLAlchemy ``create_engine`` kwargs tuned for the given
    target concurrent-user count.
    """
    return {
        "pool_size": min(target_concurrent // 10, 50),
        "max_overflow": min(target_concurrent // 5, 100),
        "pool_timeout": 30,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }
