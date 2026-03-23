"""
Tests for Deliverable 1.1 — Multi-Role Authentication API

Covers:
  - require_role() decorator / role guard
  - Signup with optional role
  - Login response includes role
  - Refresh-token response includes role
  - PUT /user-management/users/{user_id}/role (super-admin only)
  - VALID_ROLES constant
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from users.decorators import require_role, VALID_ROLES


# ---------------------------------------------------------------------------
#  Unit tests for VALID_ROLES constant
# ---------------------------------------------------------------------------

class TestValidRoles:
    def test_contains_required_roles(self):
        expected = {"user", "super-admin", "coach-admin", "org-admin", "prompt-engineer"}
        assert expected.issubset(VALID_ROLES)

    def test_admin_included(self):
        """Legacy 'admin' role must still be valid."""
        assert "admin" in VALID_ROLES


# ---------------------------------------------------------------------------
#  Unit tests for require_role() decorator / role guard
# ---------------------------------------------------------------------------

class TestRequireRole:
    """Unit tests for the flexible require_role() guard."""

    def _make_user_data(self, role: str, auth_source: str = "magic_auth"):
        return {
            "sub": "test-user-id-123",
            "email": "test@example.com",
            "user_role": role,
            "_auth_source": auth_source,
        }

    # -- Magic Auth path --

    def test_single_role_allowed(self):
        dep = require_role("super-admin")
        user_data = self._make_user_data("super-admin")
        result = dep(user_data=user_data)
        assert result["user_role"] == "super-admin"

    def test_multiple_roles_allowed(self):
        dep = require_role("super-admin", "org-admin", "coach-admin")
        user_data = self._make_user_data("org-admin")
        result = dep(user_data=user_data)
        assert result["user_role"] == "org-admin"

    def test_role_denied(self):
        dep = require_role("super-admin")
        user_data = self._make_user_data("user")
        with pytest.raises(HTTPException) as exc_info:
            dep(user_data=user_data)
        assert exc_info.value.status_code == 403

    def test_no_sub_raises_401(self):
        dep = require_role("user")
        user_data = {"email": "test@example.com", "_auth_source": "magic_auth"}
        with pytest.raises(HTTPException) as exc_info:
            dep(user_data=user_data)
        assert exc_info.value.status_code == 401

    def test_case_insensitive_matching(self):
        dep = require_role("Super-Admin")
        user_data = self._make_user_data("super-admin")
        result = dep(user_data=user_data)
        assert result["user_role"] == "super-admin"

    def test_role_info_populated(self):
        dep = require_role("user")
        user_data = self._make_user_data("user")
        result = dep(user_data=user_data)
        assert "role_info" in result
        assert result["role_info"]["role_name"] == "user"

    # -- Cognito / DB path --

    @patch("users.decorators.get_user_role_info")
    def test_cognito_role_allowed(self, mock_get_role):
        mock_get_role.return_value = {
            "user_id": "u1",
            "role_name": "coach-admin",
            "organization_id": None,
            "business_id": None,
            "is_primary": True,
            "is_active": True,
        }
        dep = require_role("coach-admin", "org-admin")
        user_data = {"sub": "u1", "email": "x@y.com", "_auth_source": "cognito"}
        result = dep(user_data=user_data)
        assert result["user_role"] == "coach-admin"

    @patch("users.decorators.get_user_role_info")
    def test_cognito_role_denied(self, mock_get_role):
        mock_get_role.return_value = {
            "user_id": "u1",
            "role_name": "user",
            "organization_id": None,
            "business_id": None,
            "is_primary": True,
            "is_active": True,
        }
        dep = require_role("super-admin")
        user_data = {"sub": "u1", "email": "x@y.com", "_auth_source": "cognito"}
        with pytest.raises(HTTPException) as exc_info:
            dep(user_data=user_data)
        assert exc_info.value.status_code == 403

    @patch("users.decorators.get_user_role_info")
    def test_cognito_no_role_info_returns_403(self, mock_get_role):
        mock_get_role.return_value = None
        dep = require_role("user")
        user_data = {"sub": "u1", "email": "x@y.com", "_auth_source": "cognito"}
        with pytest.raises(HTTPException) as exc_info:
            dep(user_data=user_data)
        assert exc_info.value.status_code == 403

    def test_prompt_engineer_role(self):
        dep = require_role("prompt-engineer")
        user_data = self._make_user_data("prompt-engineer")
        result = dep(user_data=user_data)
        assert result["user_role"] == "prompt-engineer"


# ---------------------------------------------------------------------------
#  Unit tests for signup role parameter
# ---------------------------------------------------------------------------

class TestSignupRoleParam:
    def test_signup_request_accepts_role(self):
        from users.auth_service.req_resp_parser import SignupRequest
        req = SignupRequest(
            email="test@example.com",
            password="TestPass123!",
            confirm_password="TestPass123!",
            role="coach-admin",
        )
        assert req.role == "coach-admin"

    def test_signup_request_role_defaults_to_none(self):
        from users.auth_service.req_resp_parser import SignupRequest
        req = SignupRequest(
            email="test@example.com",
            password="TestPass123!",
            confirm_password="TestPass123!",
        )
        assert req.role is None


# ---------------------------------------------------------------------------
#  Unit tests for ChangeUserRoleRequest
# ---------------------------------------------------------------------------

class TestChangeUserRoleRequest:
    def test_valid_role(self):
        from users.auth_service.req_resp_parser import ChangeUserRoleRequest
        req = ChangeUserRoleRequest(role="org-admin")
        assert req.role == "org-admin"

    def test_role_required(self):
        from users.auth_service.req_resp_parser import ChangeUserRoleRequest
        with pytest.raises(Exception):
            ChangeUserRoleRequest()


# ---------------------------------------------------------------------------
#  Integration-style tests for change-role endpoint
# ---------------------------------------------------------------------------

class TestChangeRoleEndpoint:
    """Tests for PUT /v1/user-management/users/{user_id}/role"""

    @patch("users.auth_service.user_management.ScopedSession")
    @patch("users.auth_service.user_management.require_role")
    def test_change_role_invalid_role_name(self, mock_require_role, mock_session):
        """Should reject invalid role names with 400."""
        from users.auth_service.user_management import change_user_role
        from users.auth_service.req_resp_parser import ChangeUserRoleRequest
        import json

        # Mock auth
        mock_require_role.return_value = lambda user_data: user_data

        req = ChangeUserRoleRequest(role="nonexistent-role")
        user_data = {"sub": "admin-id", "user_role": "super-admin"}

        response = change_user_role(
            role_request=req,
            user_id="some-user-id",
            user_data=user_data,
        )
        body = json.loads(response.body.decode())
        assert body["status"] is False
        assert response.status_code == 400

    @patch("users.auth_service.user_management.ScopedSession")
    @patch("users.auth_service.user_management.require_role")
    def test_change_role_user_not_found(self, mock_require_role, mock_session):
        """Should return 404 when user doesn't exist."""
        from users.auth_service.user_management import change_user_role
        from users.auth_service.req_resp_parser import ChangeUserRoleRequest
        import json

        mock_require_role.return_value = lambda user_data: user_data

        # Mock session to return no user
        mock_session_instance = MagicMock()
        mock_session.return_value = mock_session_instance
        mock_session_instance.query.return_value.filter.return_value.first.return_value = None

        req = ChangeUserRoleRequest(role="coach-admin")
        user_data = {"sub": "admin-id", "user_role": "super-admin"}

        response = change_user_role(
            role_request=req,
            user_id="nonexistent-user-id",
            user_data=user_data,
        )
        body = json.loads(response.body.decode())
        assert body["status"] is False
        assert response.status_code == 404


# ---------------------------------------------------------------------------
#  Tests for organization access helpers with new roles
# ---------------------------------------------------------------------------

class TestOrganizationAccessNewRoles:
    def test_org_admin_has_org_access(self):
        from users.decorators import check_organization_access
        user_data = {
            "user_role": "org-admin",
            "role_info": {"organization_id": "org-123"},
        }
        assert check_organization_access(user_data, "org-123") is True

    def test_org_admin_no_cross_org_access(self):
        from users.decorators import check_organization_access
        user_data = {
            "user_role": "org-admin",
            "role_info": {"organization_id": "org-123"},
        }
        assert check_organization_access(user_data, "org-999") is False

    def test_coach_admin_has_org_access(self):
        from users.decorators import check_organization_access
        user_data = {
            "user_role": "coach-admin",
            "role_info": {"organization_id": "org-123"},
        }
        assert check_organization_access(user_data, "org-123") is True

    def test_prompt_engineer_no_org_access(self):
        from users.decorators import check_organization_access
        user_data = {
            "user_role": "prompt-engineer",
            "role_info": {"organization_id": "org-123"},
        }
        assert check_organization_access(user_data, "org-123") is False

    def test_super_admin_has_all_org_access(self):
        from users.decorators import check_organization_access
        user_data = {"user_role": "super-admin", "role_info": {}}
        assert check_organization_access(user_data, "any-org-id") is True
