from __future__ import annotations

"""
Rate limiting middleware for FastAPI.

Provides per-endpoint rate limiting based on client IP or authenticated
user ID, with configurable limits per path pattern.
"""

import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# ── Rate limit configuration ─────────────────────────────────────────────
# Format: "METHOD:/path": (max_requests, window_seconds)

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "POST:/v1/login": (5, 60),
    "POST:/v1/signup": (3, 60),
    "POST:/v1/verify-signup": (5, 60),
    "POST:/v1/resend-verification": (5, 60),
    "POST:/v1/request-password-reset": (3, 60),
    "_default_authenticated": (100, 60),
    "_default_anonymous": (30, 60),
}


# ── In-memory rate limit store ────────────────────────────────────────────


class RateLimitStore:
    """
    In-memory sliding-window rate limit store.

    Maps a string key to a list of request timestamps, enforcing a maximum
    number of requests within a rolling time window.
    """

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}

    def _cleanup(self, key: str) -> None:
        """Remove expired timestamps for the given key."""
        if key not in self._store:
            return
        now = time.time()
        # Keep only timestamps within the largest possible window (60s)
        self._store[key] = [
            ts for ts in self._store[key] if (now - ts) < 120
        ]
        if not self._store[key]:
            del self._store[key]

    def check(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int, int]:
        """
        Check whether a request is allowed under the rate limit.

        Returns:
            (allowed, remaining, retry_after)
            - allowed: True if the request should proceed
            - remaining: how many requests are left in the window
            - retry_after: seconds until the client can retry (0 if allowed)
        """
        now = time.time()
        self._cleanup(key)

        timestamps = self._store.get(key, [])
        # Filter to current window
        window_start = now - window_seconds
        valid = [ts for ts in timestamps if ts > window_start]

        if len(valid) >= limit:
            # Rate limited — compute when the oldest entry in the window expires
            oldest = min(valid)
            retry_after = int(oldest + window_seconds - now) + 1
            return False, 0, max(retry_after, 1)

        # Allowed — record this request
        valid.append(now)
        self._store[key] = valid
        remaining = limit - len(valid)
        return True, remaining, 0


# ── Middleware ─────────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces per-endpoint rate limits.

    Rate limit key is derived from:
    - The ``access-token`` header (decoded user ID) when present
    - The client IP address as fallback

    Adds ``X-RateLimit-*`` headers to every response.
    """

    def __init__(self, app: Any, store: RateLimitStore | None = None) -> None:
        super().__init__(app)
        self.store = store or RateLimitStore()

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _get_client_key(request: Request) -> tuple[str, bool]:
        """
        Derive a rate-limit key and whether the caller is authenticated.

        Returns (key, is_authenticated).
        """
        token = request.headers.get("access-token")
        if token:
            try:
                # Lightweight decode — just grab the 'sub' claim without
                # full verification (auth decorators handle that).
                import json
                import base64

                parts = token.split(".")
                if len(parts) >= 2:
                    # Pad the base64 payload
                    payload = parts[1]
                    payload += "=" * (-len(payload) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(payload))
                    user_id = claims.get("sub") or claims.get("user_id")
                    if user_id:
                        return f"user:{user_id}", True
            except Exception:
                pass  # Fall through to IP-based key

        host = request.client.host if request.client else "unknown"
        return f"ip:{host}", False

    @staticmethod
    def _get_limits(method: str, path: str, is_authenticated: bool) -> tuple[int, int]:
        """Return (limit, window_seconds) for the given request."""
        route_key = f"{method}:{path}"
        if route_key in RATE_LIMITS:
            return RATE_LIMITS[route_key]

        if is_authenticated:
            return RATE_LIMITS["_default_authenticated"]
        return RATE_LIMITS["_default_anonymous"]

    # ── dispatch ──────────────────────────────────────────────────────

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        client_key, is_authenticated = self._get_client_key(request)
        method = request.method.upper()
        path = request.url.path
        limit, window = self._get_limits(method, path, is_authenticated)

        store_key = f"{client_key}:{method}:{path}"
        allowed, remaining, retry_after = self.store.check(store_key, limit, window)

        if not allowed:
            logger.warning(
                "Rate limit exceeded: key=%s path=%s limit=%d/%ds",
                client_key,
                path,
                limit,
                window,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "message": "Rate limit exceeded",
                    "status": False,
                    "error_status": {
                        "error_code": "007",
                        "description": "Try again later",
                    },
                    "data": {"retry_after": retry_after},
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )

        response = await call_next(request)

        # Attach rate-limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window)

        return response
