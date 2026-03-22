"""
Tests for Phase 3 — Role-Based Features & API Foundation (3.C1–3.C7)

Covers:
  - RBAC hierarchy enforcement (require_role_or_above)
  - VALID_ROLES includes 6 canonical roles
  - Role hierarchy ranking
  - All route modules importable with correct prefixes
  - Endpoint counts per module
  - Organization access for all new roles
  - Cost dashboard scope RBAC logic
"""
import pytest
from unittest.mock import patch
from fastapi import HTTPException

from users.decorators import (
    require_role, require_role_or_above, VALID_ROLES,
    ROLE_HIERARCHY, role_rank, check_organization_access, log_access,
)


# ---------------------------------------------------------------------------
#  3.C7 — RBAC hierarchy & VALID_ROLES
# ---------------------------------------------------------------------------

class TestRoleHierarchy:
    def test_six_canonical_roles(self):
        expected = {"user", "manager", "company-admin", "practitioner", "distributor", "super-admin"}
        assert expected.issubset(VALID_ROLES)

    def test_hierarchy_order(self):
        assert ROLE_HIERARCHY == [
            "user", "manager", "company-admin",
            "practitioner", "distributor", "super-admin",
        ]

    def test_role_rank_values(self):
        assert role_rank("user") == 0
        assert role_rank("manager") == 1
        assert role_rank("company-admin") == 2
        assert role_rank("practitioner") == 3
        assert role_rank("distributor") == 4
        assert role_rank("super-admin") == 5

    def test_unknown_role_rank(self):
        assert role_rank("nonexistent") == -1

    def test_role_rank_case_insensitive(self):
        assert role_rank("Super-Admin") == 5
        assert role_rank("MANAGER") == 1


class TestRequireRoleOrAbove:
    def _user(self, role):
        return {
            "sub": "test-123", "email": "t@t.com",
            "user_role": role, "_auth_source": "magic_auth",
        }

    def test_manager_allows_manager(self):
        dep = require_role_or_above("manager")
        r = dep(user_data=self._user("manager"))
        assert r["user_role"] == "manager"

    def test_manager_allows_super_admin(self):
        dep = require_role_or_above("manager")
        r = dep(user_data=self._user("super-admin"))
        assert r["user_role"] == "super-admin"

    def test_manager_denies_user(self):
        dep = require_role_or_above("manager")
        with pytest.raises(HTTPException) as exc:
            dep(user_data=self._user("user"))
        assert exc.value.status_code == 403

    def test_company_admin_allows_distributor(self):
        dep = require_role_or_above("company-admin")
        r = dep(user_data=self._user("distributor"))
        assert r["user_role"] == "distributor"

    def test_company_admin_denies_user(self):
        dep = require_role_or_above("company-admin")
        with pytest.raises(HTTPException) as exc:
            dep(user_data=self._user("user"))
        assert exc.value.status_code == 403

    def test_super_admin_only_allows_super_admin(self):
        dep = require_role_or_above("super-admin")
        r = dep(user_data=self._user("super-admin"))
        assert r["user_role"] == "super-admin"

    def test_super_admin_denies_distributor(self):
        dep = require_role_or_above("super-admin")
        with pytest.raises(HTTPException) as exc:
            dep(user_data=self._user("distributor"))
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
#  Organization access for all roles
# ---------------------------------------------------------------------------

class TestOrgAccessAllRoles:
    def test_super_admin_any_org(self):
        ud = {"user_role": "super-admin", "role_info": {}}
        assert check_organization_access(ud, "any-org") is True

    @pytest.mark.parametrize("role", [
        "manager", "company-admin", "practitioner", "distributor",
        "admin", "org-admin", "coach-admin",
    ])
    def test_org_scoped_own_org(self, role):
        ud = {"user_role": role, "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is True

    @pytest.mark.parametrize("role", [
        "manager", "company-admin", "practitioner", "distributor",
    ])
    def test_org_scoped_cross_org_denied(self, role):
        ud = {"user_role": role, "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-999") is False

    def test_user_role_no_org_access(self):
        ud = {"user_role": "user", "role_info": {"organization_id": "org-1"}}
        assert check_organization_access(ud, "org-1") is False


# ---------------------------------------------------------------------------
#  Model imports
# ---------------------------------------------------------------------------

class TestModelImports:
    def test_manager_models(self):
        from users.models.manager import TrainingAssignment, HiringPosition, Candidate, Interview
        assert TrainingAssignment.__tablename__ == "training_assignments"
        assert HiringPosition.__tablename__ == "hiring_positions"
        assert Candidate.__tablename__ == "candidates"
        assert Interview.__tablename__ == "interviews"

    def test_practitioner_models(self):
        from users.models.practitioner import PractitionerClient, CoachingSession, PractitionerCredits, FollowUp
        assert PractitionerClient.__tablename__ == "practitioner_clients"
        assert CoachingSession.__tablename__ == "coaching_sessions"
        assert PractitionerCredits.__tablename__ == "practitioner_credits"
        assert FollowUp.__tablename__ == "follow_ups"

    def test_distributor_models(self):
        from users.models.distributor import DistributorTerritory, DistributorPractitioner, DistributorCredits, CreditTransaction
        assert DistributorTerritory.__tablename__ == "distributor_territories"
        assert DistributorPractitioner.__tablename__ == "distributor_practitioners"
        assert DistributorCredits.__tablename__ == "distributor_credits"
        assert CreditTransaction.__tablename__ == "credit_transactions"

    def test_phase3_models(self):
        from users.models.phase3 import UserGoal, UserActivity, CostRecord, OrgNode
        assert UserGoal.__tablename__ == "user_goals"
        assert UserActivity.__tablename__ == "user_activities"
        assert CostRecord.__tablename__ == "cost_records"
        assert OrgNode.__tablename__ == "org_nodes"


# ---------------------------------------------------------------------------
#  Route imports and prefix verification
# ---------------------------------------------------------------------------

class TestRouteImports:
    def test_manager_routes(self):
        from users.manager.routes import manager_routes
        assert manager_routes.prefix == "/manager"

    def test_company_admin_routes(self):
        from users.company_admin.routes import company_admin_routes
        assert company_admin_routes.prefix == "/company-admin"

    def test_practitioner_routes(self):
        from users.practitioner.routes import practitioner_routes
        assert practitioner_routes.prefix == "/practitioner"

    def test_distributor_routes(self):
        from users.distributor.routes import distributor_routes
        assert distributor_routes.prefix == "/distributor"

    def test_user_dashboard_routes(self):
        from users.user_dashboard.routes import user_dashboard_routes
        assert user_dashboard_routes.prefix == "/user"

    def test_cost_routes(self):
        from users.costs.routes import cost_routes
        assert cost_routes.prefix == "/costs"


# ---------------------------------------------------------------------------
#  Endpoint count verification
# ---------------------------------------------------------------------------

class TestEndpointCounts:
    @staticmethod
    def _count(router):
        return len([r for r in router.routes if hasattr(r, "methods")])

    def test_manager_8_endpoints(self):
        from users.manager.routes import manager_routes
        assert self._count(manager_routes) >= 8

    def test_company_admin_10_endpoints(self):
        from users.company_admin.routes import company_admin_routes
        assert self._count(company_admin_routes) >= 10

    def test_practitioner_8_endpoints(self):
        from users.practitioner.routes import practitioner_routes
        assert self._count(practitioner_routes) >= 8

    def test_distributor_8_endpoints(self):
        from users.distributor.routes import distributor_routes
        assert self._count(distributor_routes) >= 8

    def test_user_dashboard_5_endpoints(self):
        from users.user_dashboard.routes import user_dashboard_routes
        assert self._count(user_dashboard_routes) >= 5

    def test_cost_dashboard_2_endpoints(self):
        from users.costs.routes import cost_routes
        assert self._count(cost_routes) >= 2


# ---------------------------------------------------------------------------
#  Audit logging
# ---------------------------------------------------------------------------

class TestAuditLogging:
    def test_log_access_runs(self):
        """log_access should not raise."""
        log_access({"sub": "u1", "user_role": "manager"}, "manager.team")


# ---------------------------------------------------------------------------
#  Cost dashboard scope RBAC logic
# ---------------------------------------------------------------------------

class TestCostScopeRBAC:
    """Verify role_rank thresholds used by cost_routes."""

    def test_platform_requires_super_admin(self):
        assert role_rank("super-admin") >= 5

    def test_company_requires_company_admin(self):
        assert role_rank("company-admin") >= 2

    def test_team_requires_manager(self):
        assert role_rank("manager") >= 1

    def test_user_scope_allows_all(self):
        assert role_rank("user") >= 0
