"""
Tests for edit_active_user reactivation/deactivation Cognito wiring (2026-05-13).

The /fix-user-cognito-disable change makes the Cognito enable/disable call
explicit at the call site (was implicit through update_cognito_user_attributes
-> _update_status). These tests lock in the contract so future refactors of
CognitoUserHandler can't silently drop the behavior.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest


def _user_factory(*, is_active: bool, is_deleted: bool, email: str = "x@y.com"):
    user = MagicMock()
    user.user_id = uuid.uuid4()
    user.email = email
    user.is_active = is_active
    user.is_deleted = is_deleted
    user.profile = MagicMock()
    user.profile.first_name = "X"
    user.profile.last_name = "Y"
    user.profile.is_active = is_active
    return user


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def options(self, *_):
        return self

    def filter(self, *_):
        return self

    def first(self):
        return self._result


class _FakeSession:
    def __init__(self, query_results):
        self._queue = list(query_results)
        self.committed = False
        self.added = []

    def query(self, _cls):
        return _FakeQuery(self._queue.pop(0) if self._queue else None)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture
def patch_schema_deps():
    """Patch all the Cognito + lookup helpers schema.py imports."""
    with patch("users.auth_service.schema.get_cognito_username_by_user_id", return_value="x@y.com") as g, \
         patch("users.auth_service.schema.disable_cognito_user", return_value={"status": True}) as d, \
         patch("users.auth_service.schema.enable_cognito_user", return_value={"status": True}) as e, \
         patch(
            "users.auth_service.schema.update_cognito_user_attributes",
            return_value={"status": True, "message": "ok"},
         ) as u:
        yield {"get_username": g, "disable": d, "enable": e, "update_attrs": u}


class TestEditActiveUserCognitoSync:
    """edit_active_user must explicitly enable/disable Cognito when is_active flips."""

    def _patch_session(self, fake_session):
        return patch(
            "users.auth_service.schema.ScopedSession",
            return_value=fake_session,
        )

    def test_reactivation_calls_enable_cognito(self, patch_schema_deps):
        """is_active: True flip must explicitly call enable_cognito_user."""
        from users.auth_service.schema import edit_active_user

        user = _user_factory(is_active=False, is_deleted=True)
        # Queries: Users (exists), UserInvitation (validate status)
        session = _FakeSession(query_results=[user, None])

        with self._patch_session(session):
            result = edit_active_user("x@y.com", {"is_active": True})

        assert result["success"] is True
        # User row was mutated correctly: re-activated AND un-soft-deleted
        assert user.is_active is True
        assert user.is_deleted is False
        # Defense-in-depth: explicit enable call
        patch_schema_deps["enable"].assert_called_once_with("x@y.com")
        patch_schema_deps["disable"].assert_not_called()

    def test_deactivation_via_edit_calls_disable_cognito(self, patch_schema_deps):
        """is_active: False flip via Edit must explicitly call disable_cognito_user."""
        from users.auth_service.schema import edit_active_user

        user = _user_factory(is_active=True, is_deleted=False)
        session = _FakeSession(query_results=[user, None])

        with self._patch_session(session):
            result = edit_active_user("x@y.com", {"is_active": False})

        assert result["success"] is True
        assert user.is_active is False
        # process_status_update sets is_deleted = not is_active
        assert user.is_deleted is True
        patch_schema_deps["disable"].assert_called_once_with("x@y.com")
        patch_schema_deps["enable"].assert_not_called()

    def test_name_only_edit_does_not_touch_cognito_enable_state(self, patch_schema_deps):
        """When is_active isn't in edit_data, neither enable nor disable is called."""
        from users.auth_service.schema import edit_active_user

        user = _user_factory(is_active=True, is_deleted=False)
        session = _FakeSession(query_results=[user, None])

        with self._patch_session(session):
            result = edit_active_user("x@y.com", {"first_name": "New"})

        assert result["success"] is True
        patch_schema_deps["enable"].assert_not_called()
        patch_schema_deps["disable"].assert_not_called()

    def test_cognito_flip_failure_does_not_break_edit(self, patch_schema_deps):
        """A failing enable_cognito_user is logged but doesn't fail the edit (DB already committed)."""
        from users.auth_service.schema import edit_active_user

        user = _user_factory(is_active=False, is_deleted=True)
        session = _FakeSession(query_results=[user, None])
        patch_schema_deps["enable"].side_effect = RuntimeError("cognito 500")

        with self._patch_session(session):
            result = edit_active_user("x@y.com", {"is_active": True})

        assert result["success"] is True
        assert user.is_active is True
        assert user.is_deleted is False
        # commit happened before the Cognito call
        assert session.committed is True
