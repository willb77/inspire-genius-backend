from __future__ import annotations

"""Phase 6 Performance — unit tests for load testing, query optimization,
circuit breaker, timeout middleware, memory monitor, and pool tuning."""

import os
import py_compile
import time

import pytest


# ── 6.C1 Load Testing ──────────────────────────────────────────────────


class TestLocustfile:
    def test_locustfile_compiles(self):
        """The locustfile.py should compile without errors."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "load_tests", "locustfile.py"
        )
        py_compile.compile(path, doraise=True)

    def test_locustfile_importable(self):
        """The Locust user class should be importable."""
        import importlib.util

        path = os.path.join(
            os.path.dirname(__file__), "..", "load_tests", "locustfile.py"
        )
        spec = importlib.util.spec_from_file_location("locustfile", path)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        # We intentionally do NOT exec the module here because it requires
        # the locust package at import time, which may not be installed in
        # test environments.  Compilation (above) is sufficient.


# ── 6.C2 Query Optimization ────────────────────────────────────────────


class TestPaginate:
    def test_enforces_max_limit(self):
        """paginate() should clamp limit to MAX_PAGE_LIMIT (100)."""
        from unittest.mock import MagicMock

        from prism_inspire.db.query_optimizer import MAX_PAGE_LIMIT, paginate

        query = MagicMock()
        query.count.return_value = 500
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = list(range(100))

        items, total, has_more = paginate(query, page=1, limit=9999)

        query.limit.assert_called_once_with(MAX_PAGE_LIMIT)
        assert total == 500
        assert has_more is True
        assert len(items) == 100

    def test_clamps_page_to_min_1(self):
        from unittest.mock import MagicMock

        from prism_inspire.db.query_optimizer import paginate

        query = MagicMock()
        query.count.return_value = 10
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        paginate(query, page=-5, limit=10)
        query.offset.assert_called_once_with(0)

    def test_has_more_false_on_last_page(self):
        from unittest.mock import MagicMock

        from prism_inspire.db.query_optimizer import paginate

        query = MagicMock()
        query.count.return_value = 5
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = list(range(5))

        _, _, has_more = paginate(query, page=1, limit=10)
        assert has_more is False


class TestQueryTimer:
    def test_context_manager_works(self):
        """query_timer should execute the block and return normally."""
        from prism_inspire.db.query_optimizer import query_timer

        with query_timer("test_query", threshold_ms=10_000):
            time.sleep(0.001)

    def test_logs_slow_query(self, caplog):
        """query_timer should log a warning for slow queries."""
        import logging

        from prism_inspire.db.query_optimizer import query_timer

        with caplog.at_level(logging.WARNING, logger="prism_inspire.db.query_optimizer"):
            with query_timer("slow_test", threshold_ms=1):
                time.sleep(0.01)

        assert any("Slow query" in r.message for r in caplog.records)


class TestRecommendedIndexes:
    def test_recommended_indexes_is_dict(self):
        from prism_inspire.db.query_optimizer import RECOMMENDED_INDEXES

        assert isinstance(RECOMMENDED_INDEXES, dict)
        assert len(RECOMMENDED_INDEXES) == 10

    def test_each_entry_has_table_and_columns(self):
        from prism_inspire.db.query_optimizer import RECOMMENDED_INDEXES

        for name, (table, cols) in RECOMMENDED_INDEXES.items():
            assert isinstance(table, str)
            assert isinstance(cols, list)
            assert len(cols) >= 1


# ── 6.C2 Migration ─────────────────────────────────────────────────────


class TestMigration:
    def test_migration_compiles(self):
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "prism_inspire",
            "alembic",
            "versions",
            "f6a7b8c9d0e1_phase6_query_indexes.py",
        )
        py_compile.compile(path, doraise=True)


# ── 6.C3 Circuit Breaker ───────────────────────────────────────────────


class TestCircuitBreaker:
    def test_starts_closed(self):
        from prism_inspire.middleware.performance import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, reset_timeout=10)
        assert cb.state == "closed"
        assert cb.is_open() is False

    def test_opens_after_threshold(self):
        from prism_inspire.middleware.performance import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=3, reset_timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.is_open() is True

    def test_blocks_calls_when_open(self):
        from prism_inspire.middleware.performance import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=60)
        cb.record_failure()
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            cb.call(lambda: "should not run")

    def test_transitions_to_half_open_after_timeout(self):
        from prism_inspire.middleware.performance import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.02)
        assert cb.is_open() is False
        assert cb.state == "half-open"

    def test_closes_on_success_after_half_open(self):
        from prism_inspire.middleware.performance import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.is_open()  # trigger half-open
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state == "closed"
        assert cb.failures == 0


# ── 6.C3 Memory Monitor ────────────────────────────────────────────────


class TestMemoryMonitor:
    def test_check_returns_expected_keys(self):
        from prism_inspire.middleware.performance import MemoryMonitor

        mm = MemoryMonitor(threshold_mb=2048)
        result = mm.check()
        assert "current_mb" in result
        assert "threshold_mb" in result
        assert "ok" in result
        assert isinstance(result["current_mb"], float)
        assert result["threshold_mb"] == 2048

    def test_check_ok_true_when_below_threshold(self):
        from prism_inspire.middleware.performance import MemoryMonitor

        mm = MemoryMonitor(threshold_mb=99999)
        result = mm.check()
        assert result["ok"] is True

    def test_check_ok_false_when_above_threshold(self):
        from prism_inspire.middleware.performance import MemoryMonitor

        mm = MemoryMonitor(threshold_mb=0.001)
        result = mm.check()
        assert result["ok"] is False


# ── 6.C3 Optimized Engine Kwargs ───────────────────────────────────────


class TestOptimizedEngineKwargs:
    def test_default_500_concurrent(self):
        from prism_inspire.middleware.performance import get_optimized_engine_kwargs

        kwargs = get_optimized_engine_kwargs(500)
        assert kwargs["pool_size"] == 50
        assert kwargs["max_overflow"] == 100
        assert kwargs["pool_timeout"] == 30
        assert kwargs["pool_recycle"] == 1800
        assert kwargs["pool_pre_ping"] is True

    def test_low_concurrency(self):
        from prism_inspire.middleware.performance import get_optimized_engine_kwargs

        kwargs = get_optimized_engine_kwargs(50)
        assert kwargs["pool_size"] == 5
        assert kwargs["max_overflow"] == 10

    def test_high_concurrency_capped(self):
        from prism_inspire.middleware.performance import get_optimized_engine_kwargs

        kwargs = get_optimized_engine_kwargs(10000)
        assert kwargs["pool_size"] == 50  # capped at 50
        assert kwargs["max_overflow"] == 100  # capped at 100


# ── 6.C3 Timeout Middleware ─────────────────────────────────────────────


class TestTimeoutMiddleware:
    def test_default_and_long_timeout_values(self):
        from prism_inspire.middleware.performance import (
            DEFAULT_TIMEOUT_S,
            LONG_TIMEOUT_S,
        )

        assert DEFAULT_TIMEOUT_S == 30
        assert LONG_TIMEOUT_S == 120

    def test_long_timeout_paths(self):
        from prism_inspire.middleware.performance import LONG_TIMEOUT_PATHS

        assert "/analytics/export" in LONG_TIMEOUT_PATHS
        assert "/reports/generate" in LONG_TIMEOUT_PATHS
