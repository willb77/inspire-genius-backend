"""
Tests for canonical-sub remap in monolith auth (2026-05-13).

Mirror of PR #93's agent-engine fix, applied to the monolith. Magic-Auth
users carry a sub from `magic_auth.users` that does NOT match
`public.users.user_id`; without the remap, downstream FK writes
(`files.user_id`, `chat_messages.user_id`) silently roll back.

These tests verify the lookup + cache + no-op + failure-mode contracts.
"""
import time
from unittest.mock import MagicMock, patch

import pytest


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *_):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, query_result):
        self._result = query_result
        self.closed = False

    def query(self, *_):
        return _FakeQuery(self._result)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the module-level cache between tests so they're isolated."""
    from users import auth as auth_mod
    auth_mod._SUB_CACHE.clear()
    yield
    auth_mod._SUB_CACHE.clear()


def _patch_session(query_result):
    """Patch ScopedSession to return a fake session with the given query result."""
    fake = _FakeSession(query_result)
    return patch(
        "prism_inspire.db.session.ScopedSession",
        return_value=fake,
    ), fake


class TestResolveCanonicalSub:
    """Unit tests for users.auth._resolve_canonical_sub."""

    def test_no_email_is_noop(self):
        from users.auth import _resolve_canonical_sub

        claims = {"sub": "magic-auth-sub", "_auth_source": "magic_auth"}
        _resolve_canonical_sub(claims)

        assert claims["sub"] == "magic-auth-sub"

    def test_remaps_when_email_matches_public_users(self):
        from users.auth import _resolve_canonical_sub

        # Public users row with the canonical user_id
        row = ("cognito-canonical-uuid",)
        patch_ctx, _ = _patch_session(row)

        claims = {
            "sub": "magic-auth-uuid-123",
            "email": "x@y.com",
            "_auth_source": "magic_auth",
        }

        with patch_ctx, patch("prism_inspire.db.session.ScopedSession.remove"):
            _resolve_canonical_sub(claims)

        assert claims["sub"] == "cognito-canonical-uuid"

    def test_idempotent_when_sub_already_canonical(self):
        from users.auth import _resolve_canonical_sub

        row = ("same-uuid",)
        patch_ctx, _ = _patch_session(row)

        claims = {
            "sub": "same-uuid",
            "email": "x@y.com",
            "_auth_source": "magic_auth",
        }

        with patch_ctx, patch("prism_inspire.db.session.ScopedSession.remove"):
            _resolve_canonical_sub(claims)

        # No change — sub already matched
        assert claims["sub"] == "same-uuid"

    def test_no_match_leaves_sub_unchanged(self):
        """If email isn't in public.users, do NOT swap to None — leave sub alone."""
        from users.auth import _resolve_canonical_sub

        patch_ctx, _ = _patch_session(None)

        claims = {
            "sub": "magic-auth-sub",
            "email": "unknown@y.com",
            "_auth_source": "magic_auth",
        }

        with patch_ctx, patch("prism_inspire.db.session.ScopedSession.remove"):
            _resolve_canonical_sub(claims)

        assert claims["sub"] == "magic-auth-sub"

    def test_db_failure_leaves_sub_unchanged(self):
        from users.auth import _resolve_canonical_sub

        claims = {
            "sub": "magic-auth-sub",
            "email": "x@y.com",
            "_auth_source": "magic_auth",
        }

        with patch(
            "prism_inspire.db.session.ScopedSession",
            side_effect=RuntimeError("DB unreachable"),
        ):
            _resolve_canonical_sub(claims)

        assert claims["sub"] == "magic-auth-sub"

    def test_cache_hit_skips_db_lookup(self):
        from users import auth as auth_mod
        from users.auth import _resolve_canonical_sub

        # Pre-populate cache with a valid (non-expired) entry
        auth_mod._SUB_CACHE["x@y.com"] = (
            "cached-canonical-uuid",
            time.monotonic() + 1000,
        )

        claims = {
            "sub": "magic-auth-sub",
            "email": "x@y.com",
            "_auth_source": "magic_auth",
        }

        # Patch ScopedSession to raise — proves the cache short-circuited
        with patch(
            "prism_inspire.db.session.ScopedSession",
            side_effect=AssertionError("ScopedSession should not be called on cache hit"),
        ):
            _resolve_canonical_sub(claims)

        assert claims["sub"] == "cached-canonical-uuid"

    def test_email_case_insensitive_lookup(self):
        from users.auth import _resolve_canonical_sub

        row = ("canonical-uuid",)
        patch_ctx, _ = _patch_session(row)

        # Email arrives mixed-case; lookup should still find the row
        claims = {
            "sub": "magic-auth-sub",
            "email": "X@Y.COM",
            "_auth_source": "magic_auth",
        }

        with patch_ctx, patch("prism_inspire.db.session.ScopedSession.remove"):
            _resolve_canonical_sub(claims)

        assert claims["sub"] == "canonical-uuid"

    def test_cache_eviction_when_full(self):
        """When cache hits the soft cap, oldest half is dropped."""
        from users import auth as auth_mod
        from users.auth import _resolve_canonical_sub

        # Fill cache to the soft cap
        cap = auth_mod._SUB_CACHE_MAX
        for i in range(cap):
            auth_mod._SUB_CACHE[f"u{i}@y.com"] = (
                f"sub-{i}",
                time.monotonic() + 1000,
            )

        row = ("new-canonical",)
        patch_ctx, _ = _patch_session(row)

        claims = {"sub": "x", "email": "new@y.com", "_auth_source": "magic_auth"}

        with patch_ctx, patch("prism_inspire.db.session.ScopedSession.remove"):
            _resolve_canonical_sub(claims)

        # Half should have been evicted, plus the new entry inserted
        assert len(auth_mod._SUB_CACHE) <= cap // 2 + 1
        assert auth_mod._SUB_CACHE["new@y.com"][0] == "new-canonical"
