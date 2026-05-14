"""
Tests for the User Management force-purge fix (2026-05-13).

Covers:
  - Soft delete on first call for active+verified user
  - Refusal on second call without force
  - Force-purge succeeds on already-soft-deleted user
  - Hard delete still works for unconfirmed users with pending invitations
  - FK references (issues.reported_by, organization_agents.assigned_by) are
    nulled out during hard delete so the IntegrityError landmine doesn't bite
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _user_factory(*, is_active: bool, is_email_verified: bool, is_deleted: bool, email: str = "x@y.com"):
    """Build a MagicMock Users row with the flags we care about."""
    user = MagicMock()
    user.user_id = uuid.uuid4()
    user.email = email
    user.is_active = is_active
    user.is_email_verified = is_email_verified
    user.is_deleted = is_deleted
    user.profile = MagicMock()
    return user


class _FakeQuery:
    """Minimal SQLAlchemy query stub — supports the chain used by delete_user_by_email."""

    def __init__(self, result):
        self._result = result

    def options(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self._result

    def delete(self):
        return 0


class _FakeSession:
    """Records calls; returns predictable query results based on a queue."""

    def __init__(self, query_results):
        # query_results is a list of return values for sequential .query() calls.
        self._queue = list(query_results)
        self.committed = False
        self.rolled_back = False
        self.deleted = []
        self.executed = []

    def query(self, _cls):
        return _FakeQuery(self._queue.pop(0) if self._queue else None)

    def execute(self, stmt):
        self.executed.append(stmt)
        return MagicMock()

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
#  Tests
# ---------------------------------------------------------------------------

class TestDeleteUserByEmail:
    """Unit tests for users.auth_service.schema.delete_user_by_email."""

    def _patch_session(self, fake_session):
        return patch(
            "users.auth_service.schema.ScopedSession",
            return_value=fake_session,
        )

    def test_active_user_soft_deletes_on_first_call(self):
        """First DELETE on an active+verified user soft-deletes; deletion_type=soft_delete."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=True, is_email_verified=True, is_deleted=False)
        session = _FakeSession(query_results=[user, None])  # Users, UserInvitation

        with self._patch_session(session), \
             patch("users.auth_service.schema.get_cognito_username_by_user_id", return_value="x@y.com"), \
             patch("users.auth_service.schema.disable_cognito_user") as disable, \
             patch("users.auth_service.schema.update_cognito_user_attributes"):
            result = delete_user_by_email("x@y.com")

        assert result["success"] is True
        assert result["data"]["deletion_type"] == "soft_delete"
        assert result["data"]["user_was_active"] is True
        # The user object should have been mutated to is_deleted=True
        assert user.is_deleted is True
        assert user.is_active is False
        assert session.committed is True
        # Defense-in-depth: Cognito must be explicitly disabled
        disable.assert_called_once_with("x@y.com")

    def test_active_user_soft_delete_swallows_cognito_failure(self):
        """If disable_cognito_user raises, the DB soft-delete still completes."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=True, is_email_verified=True, is_deleted=False)
        session = _FakeSession(query_results=[user, None])

        with self._patch_session(session), \
             patch(
                "users.auth_service.schema.get_cognito_username_by_user_id",
                return_value="x@y.com",
             ), \
             patch(
                "users.auth_service.schema.disable_cognito_user",
                side_effect=RuntimeError("cognito unavailable"),
             ), \
             patch("users.auth_service.schema.update_cognito_user_attributes"):
            result = delete_user_by_email("x@y.com")

        assert result["success"] is True
        assert result["data"]["deletion_type"] == "soft_delete"
        assert user.is_deleted is True
        assert session.committed is True

    def test_already_deactivated_returns_force_hint(self):
        """Second DELETE without force on a soft-deleted user returns can_force_purge=True."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=False, is_email_verified=True, is_deleted=True)
        session = _FakeSession(query_results=[user, None])

        with self._patch_session(session):
            result = delete_user_by_email("x@y.com", force=False)

        assert result["success"] is False
        assert "force=true" in result["message"].lower() or "force=true" in result["message"]
        assert result["data"]["already_soft_deleted"] is True
        assert result["data"]["can_force_purge"] is True

    def test_force_purges_soft_deleted_user(self):
        """DELETE with force=true on a soft-deleted user hard-deletes + nulls FKs."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=False, is_email_verified=True, is_deleted=True)
        # Queries: Users (with profile), UserInvitation (no pending), UserInvitation (delete in helper)
        session = _FakeSession(query_results=[user, None, None])

        with self._patch_session(session), \
             patch("users.auth_service.schema.delete_cognito_user") as cog:
            result = delete_user_by_email("x@y.com", force=True)

        assert result["success"] is True
        assert result["data"]["deletion_type"] == "hard_delete"
        assert result["data"]["cognito_deleted"] is True
        # FK null-out + profile delete + user delete should all have run
        assert len(session.executed) == 2, "expected 2 UPDATE … SET … = NULL statements"
        assert user in session.deleted
        assert user.profile in session.deleted
        cog.assert_called_once_with("x@y.com")

    def test_pending_invitation_user_hard_deletes_without_force(self):
        """Unconfirmed user with pending invitation → existing hard-delete branch still fires."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=False, is_email_verified=False, is_deleted=False)
        pending = MagicMock()
        pending.status = "PENDING"
        session = _FakeSession(query_results=[user, pending, None])

        with self._patch_session(session), \
             patch("users.auth_service.schema.delete_cognito_user"):
            result = delete_user_by_email("x@y.com", force=False)

        assert result["success"] is True
        assert result["data"]["deletion_type"] == "hard_delete"
        assert result["data"]["had_pending_invitation"] is True

    def test_cognito_delete_failure_does_not_abort_hard_delete(self):
        """Cognito errors are logged and swallowed — Aurora delete still succeeds."""
        from users.auth_service.schema import delete_user_by_email

        user = _user_factory(is_active=False, is_email_verified=True, is_deleted=True)
        session = _FakeSession(query_results=[user, None, None])

        with self._patch_session(session), \
             patch(
                "users.auth_service.schema.delete_cognito_user",
                side_effect=RuntimeError("cognito unavailable"),
             ):
            result = delete_user_by_email("x@y.com", force=True)

        assert result["success"] is True
        assert result["data"]["cognito_deleted"] is False
