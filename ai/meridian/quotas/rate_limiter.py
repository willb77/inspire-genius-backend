from __future__ import annotations

"""
Rate limiting for per-user and per-organization request throttling.
"""

from datetime import datetime, timedelta
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


class RateLimitConfig(BaseModel):
    """Rate limit configuration."""
    requests_per_minute: int = 20
    requests_per_hour: int = 200
    requests_per_day: int = 1000


class RateLimitResult(BaseModel):
    """Result of a rate limit check."""
    allowed: bool
    remaining: int
    limit: int
    reset_at: Optional[str] = None
    reason: str = ""


class RateLimiter:
    """
    Per-user and per-organization rate limiting using sliding window counters.
    """

    def __init__(self, default_config: Optional[RateLimitConfig] = None) -> None:
        self._default = default_config or RateLimitConfig()
        self._org_configs: dict[str, RateLimitConfig] = {}
        # Sliding window: key → list of timestamps
        self._windows: dict[str, list[datetime]] = {}

    def configure_org(self, org_id: str, config: RateLimitConfig) -> None:
        """Set custom rate limits for an organization."""
        self._org_configs[org_id] = config

    def check(
        self,
        user_id: str,
        org_id: Optional[str] = None,
    ) -> RateLimitResult:
        """Check if a request is allowed under rate limits."""
        config = self._org_configs.get(org_id, self._default) if org_id else self._default
        now = datetime.utcnow()
        key = f"user:{user_id}"

        if key not in self._windows:
            self._windows[key] = []

        # Prune old entries (older than 24h)
        cutoff = now - timedelta(days=1)
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]
        timestamps = self._windows[key]

        # Check per-minute
        minute_ago = now - timedelta(minutes=1)
        minute_count = sum(1 for t in timestamps if t > minute_ago)
        if minute_count >= config.requests_per_minute:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=config.requests_per_minute,
                reset_at=(minute_ago + timedelta(minutes=1)).isoformat(),
                reason="Per-minute rate limit exceeded",
            )

        # Check per-hour
        hour_ago = now - timedelta(hours=1)
        hour_count = sum(1 for t in timestamps if t > hour_ago)
        if hour_count >= config.requests_per_hour:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=config.requests_per_hour,
                reset_at=(hour_ago + timedelta(hours=1)).isoformat(),
                reason="Per-hour rate limit exceeded",
            )

        # Check per-day
        if len(timestamps) >= config.requests_per_day:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=config.requests_per_day,
                reason="Daily rate limit exceeded",
            )

        # Allowed — record timestamp
        self._windows[key].append(now)
        return RateLimitResult(
            allowed=True,
            remaining=config.requests_per_minute - minute_count - 1,
            limit=config.requests_per_minute,
        )

    def get_usage(self, user_id: str) -> dict[str, int]:
        """Get current usage counts for a user."""
        key = f"user:{user_id}"
        timestamps = self._windows.get(key, [])
        now = datetime.utcnow()
        return {
            "last_minute": sum(1 for t in timestamps if t > now - timedelta(minutes=1)),
            "last_hour": sum(1 for t in timestamps if t > now - timedelta(hours=1)),
            "last_day": len(timestamps),
        }
