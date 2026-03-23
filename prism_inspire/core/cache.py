"""
Redis / In-Memory Cache Utility
================================
Provides a unified caching interface with Redis (ElastiCache) in production
and an in-memory dict fallback for local development.

Features:
- get_cache / set_cache / invalidate / invalidate_pattern
- @cached decorator for automatic cache-through
- TTL presets for different data freshness requirements
- JSON serialization for complex objects

WS-D Phase 5 (5.D2)
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── TTL Presets (seconds) ──────────────────────────────────────
REALTIME = 300          # 5 minutes — live analytics, active dashboards
HISTORICAL = 3600       # 1 hour — historical reports, aggregations
COST_DASHBOARD = 900    # 15 minutes — cost/billing dashboards

# ── Redis client (lazy init) ──────────────────────────────────
_redis_client = None
_redis_available: bool | None = None


def _get_redis():
    """Lazy-initialize the Redis client. Returns None if unavailable."""
    global _redis_client, _redis_available

    if _redis_available is False:
        return None

    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.info("REDIS_URL not set — using in-memory cache fallback")
        _redis_available = False
        return None

    try:
        import redis
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            retry_on_timeout=True,
        )
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis cache connected: %s", redis_url.split("@")[-1])
        return _redis_client
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to in-memory cache: %s", exc)
        _redis_available = False
        _redis_client = None
        return None


# ── In-Memory Fallback Cache ──────────────────────────────────
_memory_cache: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)


def _memory_get(key: str) -> Any | None:
    entry = _memory_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if expires_at and time.time() > expires_at:
        del _memory_cache[key]
        return None
    return value


def _memory_set(key: str, value: Any, ttl: int) -> None:
    expires_at = time.time() + ttl if ttl > 0 else 0
    _memory_cache[key] = (value, expires_at)


def _memory_delete(key: str) -> None:
    _memory_cache.pop(key, None)


def _memory_delete_pattern(pattern: str) -> int:
    """Delete keys matching a glob-style pattern (supports * wildcard)."""
    regex = re.compile("^" + re.escape(pattern).replace(r"\*", ".*") + "$")
    keys_to_delete = [k for k in _memory_cache if regex.match(k)]
    for k in keys_to_delete:
        del _memory_cache[k]
    return len(keys_to_delete)


# ── Public API ─────────────────────────────────────────────────

def get_cache(key: str) -> Any | None:
    """
    Retrieve a cached value by key.
    Returns None on cache miss or expiration.
    """
    client = _get_redis()
    if client:
        try:
            raw = client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache GET error for key=%s: %s", key, exc)
            return None
    return _memory_get(key)


def set_cache(key: str, value: Any, ttl: int = REALTIME) -> None:
    """
    Store a value in the cache with a TTL (seconds).
    Complex objects are JSON-serialized.
    """
    client = _get_redis()
    if client:
        try:
            serialized = json.dumps(value, default=str)
            client.setex(key, ttl, serialized)
            return
        except Exception as exc:
            logger.warning("Cache SET error for key=%s: %s", key, exc)
    _memory_set(key, value, ttl)


def invalidate(key: str) -> None:
    """Delete a single cache entry by exact key."""
    client = _get_redis()
    if client:
        try:
            client.delete(key)
            return
        except Exception as exc:
            logger.warning("Cache INVALIDATE error for key=%s: %s", key, exc)
    _memory_delete(key)


def invalidate_pattern(pattern: str) -> int:
    """
    Delete all cache entries matching a glob pattern (e.g., 'analytics:*').
    Returns the number of keys deleted.
    """
    client = _get_redis()
    if client:
        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch = client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch)
                if cursor == 0:
                    break
            if keys:
                client.delete(*keys)
            return len(keys)
        except Exception as exc:
            logger.warning("Cache INVALIDATE_PATTERN error for pattern=%s: %s", pattern, exc)
            return 0
    return _memory_delete_pattern(pattern)


def invalidate_on_write(patterns: list[str]) -> None:
    """
    Invalidation helper — call after a write operation to bust
    related cache entries.

    Usage:
        invalidate_on_write(["analytics:*", "dashboard:summary"])
    """
    total = 0
    for pattern in patterns:
        if "*" in pattern:
            total += invalidate_pattern(pattern)
        else:
            invalidate(pattern)
            total += 1
    if total:
        logger.debug("Invalidated %d cache entries for patterns: %s", total, patterns)


# ── Cache Decorator ────────────────────────────────────────────

def cached(ttl: int = REALTIME, key_prefix: str = "cache") -> Callable:
    """
    Decorator that caches function results.

    Usage:
        @cached(ttl=HISTORICAL, key_prefix="analytics")
        def get_monthly_report(org_id: str, month: str) -> dict:
            ...

    The cache key is built from the prefix + function name + argument hash.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build cache key from arguments
            arg_key = hashlib.md5(
                json.dumps({"args": args, "kwargs": kwargs}, default=str).encode()
            ).hexdigest()[:12]
            cache_key = f"{key_prefix}:{func.__name__}:{arg_key}"

            # Try cache first
            result = get_cache(cache_key)
            if result is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return result

            # Cache miss — call function and store result
            logger.debug("Cache MISS: %s", cache_key)
            result = func(*args, **kwargs)
            if result is not None:
                set_cache(cache_key, result, ttl)
            return result

        # Expose cache key builder for manual invalidation
        wrapper.cache_prefix = f"{key_prefix}:{func.__name__}"  # type: ignore[attr-defined]
        return wrapper

    return decorator


def cached_async(ttl: int = REALTIME, key_prefix: str = "cache") -> Callable:
    """
    Async version of the @cached decorator.

    Usage:
        @cached_async(ttl=COST_DASHBOARD, key_prefix="costs")
        async def get_cost_summary(org_id: str) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            arg_key = hashlib.md5(
                json.dumps({"args": args, "kwargs": kwargs}, default=str).encode()
            ).hexdigest()[:12]
            cache_key = f"{key_prefix}:{func.__name__}:{arg_key}"

            result = get_cache(cache_key)
            if result is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return result

            logger.debug("Cache MISS: %s", cache_key)
            result = await func(*args, **kwargs)
            if result is not None:
                set_cache(cache_key, result, ttl)
            return result

        wrapper.cache_prefix = f"{key_prefix}:{func.__name__}"  # type: ignore[attr-defined]
        return wrapper

    return decorator
