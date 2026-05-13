"""
Tests for purge_inactive_users() — server-side bulk purge of soft-deleted users.

The /fix-user-purge-endpoint change replaced a client-side fanout with a
single backend endpoint that iterates is_deleted=True users inside savepoints.
These tests lock in:
  - All soft-deleted users get hard-deleted
  - Active users are untouched
  - One failure doesn't abort the rest (savepoint isolation)
  - Empty input returns total=0 without error
"""
import uuid
from unittest.mock import MagicMock, patch


def _user_factory(*, email: str, is_deleted: bool = True):
    user = MagicMock()
    user.user_id = uuid.uuid4()
    user.email = email
    user.is_deleted = is_deleted
    user.profile = MagicMock()
    return user


class _FakeQuery:
    """SQLAlchemy query stub — supports .filter(...).all() and .filter(...).first()."""

    def __init__(self, results):
        # results may be a list (for .all()) OR a single value (for .first()).
        self._results = results

    def filter(self, *_):
        return self

    def all(self):
        return self._results if isinstance(self._results, list) else [self._results]

    def first(self):
        if isinstance(self._results, list):
            return self._results[0] if self._results else None
        return self._results

    def delete(self):
        return 0


class _FakeSavepoint:
    def __init__(self, session):
        self._session = session
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True
        self._session.savepoints_committed += 1

    def rollback(self):
        self.rolled_back = True
        self._session.savepoints_rolled_back += 1


class _FakeSession:
    """Returns query results in declared order; tracks savepoints."""

    def __init__(self, query_results):
        # query_results is a list of (queue) values returned by sequential .query() calls.
        self._queue = list(query_results)
        self.committed = False
        self.rolled_back = False
        self.savepoints_committed = 0
        self.savepoints_rolled_back = 0
        self.deleted = []
        self.executed = []

    def query(self, _cls):
        return _FakeQuery(self._queue.pop(0) if self._queue else None)

    def begin_nested(self):
        return _FakeSavepoint(self)

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
        pass


class TestPurgeInactiveUsers:
    """Unit tests for users.auth_service.schema.purge_inactive_users."""

    def _patch_session(self, fake):
        return patch("users.auth_service.schema.ScopedSession", return_value=fake)

    def test_empty_input_returns_total_zero(self):
        from users.auth_service.schema import purge_inactive_users

        session = _FakeSession(query_results=[[]])

        with self._patch_session(session):
            result = purge_inactive_users()

        assert result["success"] is True
        assert result["data"] == {"total": 0, "succeeded": [], "failed": []}

    def test_all_inactive_users_succeed(self):
        from users.auth_service.schema import purge_inactive_users

        users = [
            _user_factory(email="a@x.com"),
            _user_factory(email="b@x.com"),
            _user_factory(email="c@x.com"),
        ]
        # Queue: [list of users for .all()] then None (UserInvitation .first()) per user.
        # _hard_delete_user also calls session.query(UserInvitation).filter(...).delete()
        # which goes through the same .query() — so 1 + (2 * 3) = 7 queue entries.
        session = _FakeSession(query_results=[users] + [None, None] * 3)

        with self._patch_session(session), \
             patch("users.auth_service.schema.delete_cognito_user"):
            result = purge_inactive_users()

        assert result["success"] is True
        assert result["data"]["total"] == 3
        assert set(result["data"]["succeeded"]) == {"a@x.com", "b@x.com", "c@x.com"}
        assert result["data"]["failed"] == []
        # All three savepoints committed
        assert session.savepoints_committed == 3
        assert session.savepoints_rolled_back == 0

    def test_one_failure_does_not_abort_others(self):
        """If _hard_delete_user raises for one user, the others still succeed."""
        from users.auth_service.schema import purge_inactive_users

        users = [
            _user_factory(email="ok1@x.com"),
            _user_factory(email="bad@x.com"),
            _user_factory(email="ok2@x.com"),
        ]
        session = _FakeSession(query_results=[users] + [None, None] * 3)

        # Patch _hard_delete_user to raise for "bad@x.com" only
        from users.auth_service import schema as schema_mod
        original = schema_mod._hard_delete_user

        def selective_delete(session, user, email, pending):
            if email == "bad@x.com":
                raise RuntimeError("IntegrityError: FK violation on issue_comments")
            return original(session, user, email, pending)

        with self._patch_session(session), \
             patch("users.auth_service.schema._hard_delete_user", side_effect=selective_delete), \
             patch("users.auth_service.schema.delete_cognito_user"):
            result = purge_inactive_users()

        assert result["success"] is True
        assert result["data"]["total"] == 3
        assert set(result["data"]["succeeded"]) == {"ok1@x.com", "ok2@x.com"}
        assert len(result["data"]["failed"]) == 1
        assert result["data"]["failed"][0]["email"] == "bad@x.com"
        assert "FK violation" in result["data"]["failed"][0]["reason"]
        # Two savepoints committed, one rolled back
        assert session.savepoints_committed == 2
        assert session.savepoints_rolled_back == 1

    def test_failure_reason_truncated_to_200_chars(self):
        from users.auth_service.schema import purge_inactive_users

        users = [_user_factory(email="long@x.com")]
        session = _FakeSession(query_results=[users, None, None])
        big_message = "x" * 500

        with self._patch_session(session), \
             patch(
                "users.auth_service.schema._hard_delete_user",
                side_effect=RuntimeError(big_message),
             ):
            result = purge_inactive_users()

        assert len(result["data"]["failed"][0]["reason"]) <= 200

    def test_outer_exception_returns_error_envelope(self):
        """If the initial query itself fails, the function returns success:false."""
        from users.auth_service.schema import purge_inactive_users

        session = _FakeSession(query_results=[])

        # Force .query() to raise
        with self._patch_session(session), \
             patch.object(
                _FakeSession, "query",
                side_effect=RuntimeError("db unreachable"),
             ):
            result = purge_inactive_users()

        assert result["success"] is False
        assert "db unreachable" in result["message"]
