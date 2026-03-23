"""
Cache-Control Middleware for FastAPI
=====================================
Adds Cache-Control response headers based on URL path patterns.

Path-specific caching rules:
- /v1/analytics/*  → private, max-age=300  (5 min)
- /v1/dashboard/*  → private, max-age=900  (15 min)
- /v1/costs/*      → private, max-age=900  (15 min)
- /health*         → no-cache
- All other /v1/*  → no-store (assumed writes / dynamic)

WS-D Phase 5 (5.D2)
"""

from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── Path → Cache-Control mapping ──────────────────────────────
# Checked in order; first match wins.
_CACHE_RULES: list[tuple[str, str]] = [
    # Analytics endpoints — 5-minute private cache
    ("/v1/analytics", "private, max-age=300"),

    # Dashboard endpoints — 15-minute private cache
    ("/v1/dashboard", "private, max-age=900"),

    # Cost endpoints — 15-minute private cache
    ("/v1/costs", "private, max-age=900"),

    # Health checks — never cache
    ("/health", "no-cache, no-store, must-revalidate"),
]

# Default for all other /v1/* paths (writes, auth, etc.)
_DEFAULT_API_CACHE = "no-store"


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware that sets Cache-Control headers on responses based on
    the request path. Only applies to GET responses — POST/PUT/PATCH/DELETE
    always get no-store.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Skip if response already has Cache-Control set by the route handler
        if "cache-control" in response.headers:
            return response

        path = request.url.path

        # Non-GET methods always get no-store
        if request.method not in ("GET", "HEAD"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return response

        # Match path against rules
        cache_control = self._resolve_cache_control(path)
        response.headers["Cache-Control"] = cache_control

        # Add Pragma: no-cache for no-store / no-cache responses (HTTP/1.0 compat)
        if "no-store" in cache_control or "no-cache" in cache_control:
            response.headers["Pragma"] = "no-cache"

        return response

    @staticmethod
    def _resolve_cache_control(path: str) -> str:
        """Determine the Cache-Control value for a given path."""
        for prefix, cache_value in _CACHE_RULES:
            if path.startswith(prefix):
                return cache_value

        # All other API paths default to no-store
        if path.startswith("/v1/"):
            return _DEFAULT_API_CACHE

        # Non-API paths (static files, etc.) — let CloudFront handle it
        return "public, max-age=0, must-revalidate"
