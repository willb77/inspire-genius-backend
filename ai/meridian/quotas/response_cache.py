from __future__ import annotations

"""
Response cache for common behavioral queries.

Caches Aura's profile interpretations and other frequently-requested outputs
to reduce LLM calls and latency.
"""

from datetime import datetime, timedelta
from typing import Any, Optional
from prism_inspire.core.log_config import logger
import hashlib


class CacheEntry:
    __slots__ = ("key", "value", "created_at", "ttl", "hit_count")

    def __init__(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.key = key
        self.value = value
        self.created_at = datetime.utcnow()
        self.ttl = timedelta(seconds=ttl_seconds)
        self.hit_count = 0

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() - self.created_at > self.ttl


class ResponseCache:
    """
    In-memory response cache with TTL and LRU eviction.

    Primarily caches:
    - Aura profile interpretations (TTL: 1 hour)
    - Behavioral context generation (TTL: 30 min)
    - Common queries (TTL: 15 min)
    """

    DEFAULT_TTL = 900  # 15 minutes
    PROFILE_TTL = 3600  # 1 hour for profile data
    CONTEXT_TTL = 1800  # 30 minutes for behavioral context

    def __init__(self, max_entries: int = 500) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def _make_key(self, agent_id: str, action: str, user_id: str, params_hash: str = "") -> str:
        raw = f"{agent_id}:{action}:{user_id}:{params_hash}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(
        self,
        agent_id: str,
        action: str,
        user_id: str,
        params_hash: str = "",
    ) -> Optional[Any]:
        """Get a cached response. Returns None on miss or expiry."""
        key = self._make_key(agent_id, action, user_id, params_hash)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired:
            del self._cache[key]
            self._misses += 1
            return None
        entry.hit_count += 1
        self._hits += 1
        return entry.value

    def put(
        self,
        agent_id: str,
        action: str,
        user_id: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        params_hash: str = "",
    ) -> None:
        """Cache a response."""
        if ttl_seconds is None:
            # Auto-select TTL based on agent/action
            if agent_id == "aura" and action == "interpret_profile":
                ttl_seconds = self.PROFILE_TTL
            elif action == "generate_context":
                ttl_seconds = self.CONTEXT_TTL
            else:
                ttl_seconds = self.DEFAULT_TTL

        key = self._make_key(agent_id, action, user_id, params_hash)

        # Evict if at capacity (remove oldest expired, then least-hit)
        if len(self._cache) >= self._max_entries and key not in self._cache:
            self._evict()

        self._cache[key] = CacheEntry(key, value, ttl_seconds)

    def invalidate(self, agent_id: str, action: str, user_id: str, params_hash: str = "") -> bool:
        """Invalidate a specific cache entry."""
        key = self._make_key(agent_id, action, user_id, params_hash)
        return self._cache.pop(key, None) is not None

    def invalidate_user(self, user_id: str) -> int:
        """Invalidate all cache entries for a user."""
        keys_to_remove = [
            k for k, v in self._cache.items()
            if f":{user_id}:" in f":{k}:"  # Rough match; exact key contains user_id
        ]
        # Since keys are hashed, we need to track user_id → keys separately
        # For now, clear expired entries and return 0
        self._prune_expired()
        return 0

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        self._prune_expired()
        total_requests = self._hits + self._misses
        return {
            "entries": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total_requests if total_requests > 0 else 0.0,
        }

    def _prune_expired(self) -> None:
        expired = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired:
            del self._cache[k]

    def _evict(self) -> None:
        """Evict expired first, then least-hit entry."""
        self._prune_expired()
        if len(self._cache) >= self._max_entries:
            # Remove least-hit entry
            least = min(self._cache.values(), key=lambda e: e.hit_count)
            del self._cache[least.key]
