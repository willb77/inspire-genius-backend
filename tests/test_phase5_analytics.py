from __future__ import annotations

"""Phase 5 Analytics — unit tests for models, routes, RBAC, and helpers."""

import pytest
from datetime import date, timedelta


# ── Model imports & table names ──────────────────────────────────────
class TestModels:
    def test_report_model_imports(self):
        from users.models.analytics import Report
        assert Report.__tablename__ == "reports"

    def test_export_job_model_imports(self):
        from users.models.analytics import ExportJob
        assert ExportJob.__tablename__ == "export_jobs"

    def test_report_columns(self):
        from users.models.analytics import Report
        col_names = {c.name for c in Report.__table__.columns}
        expected = {
            "id", "user_id", "report_type", "title", "status", "format",
            "file_url", "file_key", "parameters_json", "error_message",
            "scheduled_cron", "created_at", "completed_at", "updated_at",
            "is_deleted",
        }
        assert expected.issubset(col_names)

    def test_export_job_columns(self):
        from users.models.analytics import ExportJob
        col_names = {c.name for c in ExportJob.__table__.columns}
        expected = {
            "id", "user_id", "scope", "format", "status", "progress_pct",
            "result_url", "result_key", "error_message", "total_records",
            "created_at", "completed_at",
        }
        assert expected.issubset(col_names)


# ── Route imports & prefixes ─────────────────────────────────────────
class TestRouteImports:
    def test_analytics_routes_import(self):
        from users.analytics.routes import analytics_routes
        assert analytics_routes.prefix == "/analytics"

    def test_report_routes_import(self):
        from users.analytics.report_routes import report_routes
        assert report_routes.prefix == "/reports"

    def test_export_routes_import(self):
        from users.analytics.export_routes import export_routes
        assert export_routes.prefix == "/analytics"


# ── Endpoint counts ─────────────────────────────────────────────────
class TestEndpointCounts:
    def test_analytics_has_4_endpoints(self):
        from users.analytics.routes import analytics_routes
        assert len(analytics_routes.routes) == 4

    def test_report_has_3_endpoints(self):
        from users.analytics.report_routes import report_routes
        assert len(report_routes.routes) == 3

    def test_export_has_3_endpoints(self):
        from users.analytics.export_routes import export_routes
        assert len(export_routes.routes) == 3

    def test_total_10_endpoints(self):
        from users.analytics.routes import analytics_routes
        from users.analytics.report_routes import report_routes
        from users.analytics.export_routes import export_routes
        total = len(analytics_routes.routes) + len(report_routes.routes) + len(export_routes.routes)
        assert total == 10


# ── RBAC checks ─────────────────────────────────────────────────────
class TestRBAC:
    def test_analytics_user_allows_any_auth(self):
        """GET /analytics/user uses require_authenticated_user — any role works."""
        from users.analytics.routes import analytics_routes
        user_route = [r for r in analytics_routes.routes if r.path == "/user"]
        assert len(user_route) == 1

    def test_analytics_company_requires_company_admin(self):
        """GET /analytics/company uses require_role_or_above('company-admin')."""
        from users.analytics.routes import analytics_routes
        company_route = [r for r in analytics_routes.routes if r.path == "/company"]
        assert len(company_route) == 1

    def test_analytics_platform_requires_super_admin(self):
        """GET /analytics/platform uses require_role('super-admin')."""
        from users.analytics.routes import analytics_routes
        platform_route = [r for r in analytics_routes.routes if r.path == "/platform"]
        assert len(platform_route) == 1

    def test_analytics_manager_team_requires_manager(self):
        """GET /analytics/manager/team uses require_role_or_above('manager')."""
        from users.analytics.routes import analytics_routes
        mgr_route = [r for r in analytics_routes.routes if r.path == "/manager/team"]
        assert len(mgr_route) == 1


# ── Date parsing helper ─────────────────────────────────────────────
class TestDateParsing:
    def test_parse_date_range_defaults(self):
        from users.analytics.routes import _parse_date_range
        start, end = _parse_date_range(None, None)
        assert end == date.today()
        assert start == date.today() - timedelta(days=180)

    def test_parse_date_range_custom(self):
        from users.analytics.routes import _parse_date_range
        start, end = _parse_date_range("2026-01-01", "2026-06-30")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 6, 30)

    def test_parse_date_range_invalid_falls_back(self):
        from users.analytics.routes import _parse_date_range
        start, end = _parse_date_range("not-a-date", "also-not")
        # Should fall back gracefully
        assert isinstance(start, date)
        assert isinstance(end, date)


# ── Export scope RBAC checks ─────────────────────────────────────────
class TestExportScopeAccess:
    def test_scope_min_rank_values(self):
        from users.analytics.export_routes import SCOPE_MIN_RANK
        assert SCOPE_MIN_RANK["platform"] == 5
        assert SCOPE_MIN_RANK["company"] == 2
        assert SCOPE_MIN_RANK["team"] == 1
        assert SCOPE_MIN_RANK["user"] == 0

    def test_check_export_scope_user_allows_any(self):
        from users.analytics.export_routes import _check_export_scope_access
        result = _check_export_scope_access({"user_role": "user"}, "user")
        assert result is None

    def test_check_export_scope_platform_denies_user(self):
        from users.analytics.export_routes import _check_export_scope_access
        result = _check_export_scope_access({"user_role": "user"}, "platform")
        assert result is not None
        assert "Access denied" in result

    def test_check_export_scope_platform_allows_super_admin(self):
        from users.analytics.export_routes import _check_export_scope_access
        result = _check_export_scope_access({"user_role": "super-admin"}, "platform")
        assert result is None

    def test_check_export_scope_company_allows_company_admin(self):
        from users.analytics.export_routes import _check_export_scope_access
        result = _check_export_scope_access({"user_role": "company-admin"}, "company")
        assert result is None

    def test_check_export_scope_company_denies_manager(self):
        from users.analytics.export_routes import _check_export_scope_access
        result = _check_export_scope_access({"user_role": "manager"}, "company")
        assert result is not None


# ── CSV serializer ───────────────────────────────────────────────────
class TestCSVSerializer:
    def test_serialize_empty(self):
        from users.analytics.export_routes import _serialize_csv
        assert _serialize_csv([]) == ""

    def test_serialize_rows(self):
        from users.analytics.export_routes import _serialize_csv
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = _serialize_csv(rows)
        assert "a" in result
        assert "b" in result
        assert "1" in result
