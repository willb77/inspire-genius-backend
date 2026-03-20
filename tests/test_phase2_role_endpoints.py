"""
Tests for Phase 2 — Multi-Role API Endpoints (2.1–2.4)

Covers:
  - Role guard enforcement on all new endpoints
  - VALID_ROLES includes the 6 canonical roles
  - Data shape verification for each endpoint
  - Organization access helpers with new roles
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from users.decorators import require_role, VALID_ROLES, check_organization_access


# ---------------------------------------------------------------------------
#  VALID_ROLES updated for 6-role system
# ---------------------------------------------------------------------------

class TestValidRolesPhase2:
    def test_six_canonical_roles(self):
        expected = {"user", "manager", "company-admin", "practitioner", "distributor", "super-admin"}
        assert expected.issubset(VALID_ROLES)

    def test_legacy_roles_still_present(self):
        for role in ("admin", "coach-admin", "org-admin", "prompt-engineer"):
            assert role in VALID_ROLES


# ---------------------------------------------------------------------------
#  Role guard tests for new roles
# ---------------------------------------------------------------------------

class TestRequireRolePhase2:
    def _user(self, role):
        return {
            "sub": "test-user-123",
            "email": "test@example.com",
            "user_role": role,
            "_auth_source": "magic_auth",
        }

    def test_manager_role_allowed(self):
        dep = require_role("manager", "super-admin")
        result = dep(user_data=self._user("manager"))
        assert result["user_role"] == "manager"

    def test_company_admin_role_allowed(self):
        dep = require_role("company-admin", "super-admin")
        result = dep(user_data=self._user("company-admin"))
        assert result["user_role"] == "company-admin"

    def test_practitioner_role_allowed(self):
        dep = require_role("practitioner", "super-admin")
        result = dep(user_data=self._user("practitioner"))
        assert result["user_role"] == "practitioner"

    def test_distributor_role_allowed(self):
        dep = require_role("distributor", "super-admin")
        result = dep(user_data=self._user("distributor"))
        assert result["user_role"] == "distributor"

    def test_user_denied_manager_endpoint(self):
        dep = require_role("manager")
        with pytest.raises(HTTPException) as exc:
            dep(user_data=self._user("user"))
        assert exc.value.status_code == 403

    def test_practitioner_denied_distributor_endpoint(self):
        dep = require_role("distributor")
        with pytest.raises(HTTPException) as exc:
            dep(user_data=self._user("practitioner"))
        assert exc.value.status_code == 403

    def test_super_admin_can_access_all(self):
        for guard_roles in [("manager",), ("company-admin",), ("practitioner",), ("distributor",)]:
            dep = require_role(*guard_roles, "super-admin")
            result = dep(user_data=self._user("super-admin"))
            assert result["user_role"] == "super-admin"


# ---------------------------------------------------------------------------
#  Organization access for new roles
# ---------------------------------------------------------------------------

class TestOrgAccessPhase2:
    def test_manager_org_access(self):
        ud = {"user_role": "manager", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is True
        assert check_organization_access(ud, "org-2") is False

    def test_company_admin_org_access(self):
        ud = {"user_role": "company-admin", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is True

    def test_practitioner_org_access(self):
        ud = {"user_role": "practitioner", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is True

    def test_distributor_org_access(self):
        ud = {"user_role": "distributor", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is True

    def test_user_no_org_access(self):
        ud = {"user_role": "user", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is False


# ---------------------------------------------------------------------------
#  Model import tests — verify all new models are importable
# ---------------------------------------------------------------------------

class TestModelImports:
    def test_manager_models(self):
        from users.models.manager import (
            TrainingAssignment, HiringPosition, Candidate, Interview,
            TrainingStatusEnum, PositionStatusEnum, CandidateStatusEnum, InterviewStatusEnum,
        )
        assert TrainingAssignment.__tablename__ == "training_assignments"
        assert HiringPosition.__tablename__ == "hiring_positions"
        assert Candidate.__tablename__ == "candidates"
        assert Interview.__tablename__ == "interviews"

    def test_practitioner_models(self):
        from users.models.practitioner import (
            PractitionerClient, CoachingSession, PractitionerCredit, FollowUp,
            SessionStatusEnum, FollowUpPriorityEnum, FollowUpStatusEnum,
        )
        assert PractitionerClient.__tablename__ == "practitioner_clients"
        assert CoachingSession.__tablename__ == "coaching_sessions"
        assert PractitionerCredit.__tablename__ == "practitioner_credits"
        assert FollowUp.__tablename__ == "follow_ups"

    def test_distributor_models(self):
        from users.models.distributor import (
            DistributorTerritory, DistributorPractitioner,
            DistributorCredit, CreditTransaction, TransactionTypeEnum,
        )
        assert DistributorTerritory.__tablename__ == "distributor_territories"
        assert DistributorPractitioner.__tablename__ == "distributor_practitioners"
        assert DistributorCredit.__tablename__ == "distributor_credits"
        assert CreditTransaction.__tablename__ == "credit_transactions"


# ---------------------------------------------------------------------------
#  Route import tests — verify all route modules are importable
# ---------------------------------------------------------------------------

class TestRouteImports:
    def test_manager_routes(self):
        from users.manager.routes import manager_routes
        assert manager_routes.prefix == "/managers"

    def test_company_admin_routes(self):
        from users.company_admin.routes import company_admin_routes
        assert company_admin_routes.prefix == "/company-admin"

    def test_practitioner_routes(self):
        from users.practitioner.routes import practitioner_routes
        assert practitioner_routes.prefix == "/practitioners"

    def test_distributor_routes(self):
        from users.distributor.routes import distributor_routes
        assert distributor_routes.prefix == "/distributors"


# ---------------------------------------------------------------------------
#  Endpoint count verification
# ---------------------------------------------------------------------------

class TestEndpointCounts:
    def test_manager_has_6_endpoints(self):
        from users.manager.routes import manager_routes
        # GET team, GET activity, POST training, GET hiring, GET interviews, POST invite
        routes = [r for r in manager_routes.routes if hasattr(r, "methods")]
        assert len(routes) == 6

    def test_company_admin_has_8_endpoints(self):
        from users.company_admin.routes import company_admin_routes
        routes = [r for r in company_admin_routes.routes if hasattr(r, "methods")]
        assert len(routes) == 8

    def test_practitioner_has_6_endpoints(self):
        from users.practitioner.routes import practitioner_routes
        routes = [r for r in practitioner_routes.routes if hasattr(r, "methods")]
        assert len(routes) == 6

    def test_distributor_has_6_endpoints(self):
        from users.distributor.routes import distributor_routes
        routes = [r for r in distributor_routes.routes if hasattr(r, "methods")]
        assert len(routes) == 6
