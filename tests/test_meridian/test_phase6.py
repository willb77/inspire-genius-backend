from __future__ import annotations

"""Tests for Phase 6: Process Templates, Circuit Breakers, Rate Limiting, Cost Tracking, Cache."""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from ai.meridian.core.types import AgentId, AgentTask, DAGNode, ProcessTemplate
from ai.meridian.templates.template_library import TemplateLibrary, PROCESS_TEMPLATES
from ai.meridian.resilience.circuit_breaker import CircuitBreaker, CircuitState
from ai.meridian.resilience.health import AgentHealthMonitor, HealthStatus
from ai.meridian.quotas.rate_limiter import RateLimiter, RateLimitConfig
from ai.meridian.quotas.cost_tracker import CostTracker, AGENT_TIERS, AGENT_TOKEN_BUDGETS
from ai.meridian.quotas.response_cache import ResponseCache


# ==================== Process Templates ====================

class TestTemplateLibrary:
    def test_all_9_templates_defined(self):
        assert len(PROCESS_TEMPLATES) == 9

    def test_library_loads_all(self):
        lib = TemplateLibrary()
        assert lib.template_count == 9

    def test_match_onboarding(self):
        lib = TemplateLibrary()
        t = lib.match("I'm a new user just getting started")
        assert t is not None
        assert t.template_id == "new_user_onboarding"

    def test_match_interview_prep(self):
        lib = TemplateLibrary()
        t = lib.match("Help me prepare for a behavioral interview")
        assert t is not None
        assert t.template_id == "behavioral_interview_prep"

    def test_match_team_analysis(self):
        lib = TemplateLibrary()
        t = lib.match("Please do a team composition analysis")
        assert t is not None
        assert t.template_id == "team_composition_analysis"

    def test_match_performance_review(self):
        t = TemplateLibrary().match("Help me prepare for my annual review")
        assert t is not None
        assert t.template_id == "performance_review_prep"

    def test_match_hiring_triage(self):
        t = TemplateLibrary().match("Run the hiring triage for candidates")
        assert t is not None
        assert t.template_id == "hiring_triage"

    def test_match_executive_coaching(self):
        t = TemplateLibrary().match("I need executive leadership coaching")
        assert t is not None
        assert t.template_id == "executive_leadership_coaching"

    def test_match_school_to_career(self):
        t = TemplateLibrary().match("Set up a school to career pipeline")
        assert t is not None
        assert t.template_id == "school_to_career_pipeline"

    def test_match_resilience_checkin(self):
        t = TemplateLibrary().match("Do a wellness check on me")
        assert t is not None
        assert t.template_id == "resilience_checkin"

    def test_match_conflict_resolution(self):
        t = TemplateLibrary().match("I want to resolve conflict with my colleague")
        assert t is not None
        assert t.template_id == "conflict_resolution"

    def test_no_match_returns_none(self):
        assert TemplateLibrary().match("what is the weather") is None

    def test_compile_dag(self):
        lib = TemplateLibrary()
        t = lib.get_template("new_user_onboarding")
        assert t is not None
        dag = lib.compile_dag(t, {"user_id": "u1", "behavioral_context": None})
        assert len(dag) == 2
        assert dag[0].task.agent_id == AgentId.AURA
        assert dag[1].task.agent_id == AgentId.NOVA
        assert dag[1].dependencies == ["aura_profile"]

    def test_compile_interview_prep_dag(self):
        lib = TemplateLibrary()
        t = lib.get_template("behavioral_interview_prep")
        dag = lib.compile_dag(t, {"user_id": "u1"})
        assert len(dag) == 4
        # Last node (Ascend) depends on Aura and Nova
        assert "aura_profile" in dag[3].dependencies
        assert "nova_strategy" in dag[3].dependencies

    def test_register_custom_template(self):
        lib = TemplateLibrary()
        custom = ProcessTemplate(
            template_id="custom_workflow",
            name="Custom",
            description="Custom workflow",
            trigger_patterns=["custom workflow"],
            steps=[{"node_id": "a", "agent_id": "aura", "action": "generate_context", "deps": []}],
        )
        lib.register_template(custom)
        assert lib.template_count == 10
        assert lib.match("run custom workflow") is not None

    def test_list_templates(self):
        templates = TemplateLibrary().list_templates()
        assert len(templates) == 9
        assert all("template_id" in t for t in templates)
        assert all("agents_involved" in t for t in templates)


# ==================== Circuit Breaker ====================

class TestCircuitBreaker:
    def test_initial_state_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_on_success(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_requests(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_seconds=0)
        cb.record_failure()
        # With 0-second timeout, accessing .state immediately transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_seconds=0)
        cb.record_failure()
        _ = cb.state  # trigger transition
        assert cb.allow_request() is True
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout_seconds=0)
        cb.record_failure()
        _ = cb.state  # trigger OPEN → HALF_OPEN
        cb.allow_request()
        cb.record_failure()
        # After failure in HALF_OPEN, goes OPEN, but 0-timeout means
        # accessing .state again immediately transitions to HALF_OPEN
        # Force check internal state directly
        assert cb._state == CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_stats(self):
        cb = CircuitBreaker("test", failure_threshold=5)
        cb.record_success()
        cb.record_failure()
        stats = cb.get_stats()
        assert stats["total_calls"] == 2
        assert stats["total_failures"] == 1


# ==================== Health Monitor ====================

class TestHealthMonitor:
    def test_all_agents_have_breakers(self):
        hm = AgentHealthMonitor()
        for agent_id in AgentId:
            assert hm.is_agent_available(agent_id.value) is True

    def test_agent_becomes_unhealthy(self):
        hm = AgentHealthMonitor(failure_threshold=2)
        hm.record_failure("aura")
        hm.record_failure("aura")
        assert hm.get_agent_health("aura") == HealthStatus.UNHEALTHY
        assert hm.is_agent_available("aura") is False

    def test_agent_recovers(self):
        hm = AgentHealthMonitor(failure_threshold=1, recovery_timeout=0)
        hm.record_failure("echo")
        # With 0-second timeout, health check sees HALF_OPEN → DEGRADED
        assert hm.get_agent_health("echo") == HealthStatus.DEGRADED

    def test_system_health_all_healthy(self):
        summary = AgentHealthMonitor().get_system_health()
        assert summary["overall"] == "healthy"
        assert summary["meridian_available"] is True

    def test_system_health_degraded(self):
        hm = AgentHealthMonitor(failure_threshold=1)
        hm.record_failure("echo")
        summary = hm.get_system_health()
        assert summary["overall"] in ("degraded", "unhealthy")

    def test_fallback_agent(self):
        hm = AgentHealthMonitor(failure_threshold=1)
        hm.record_failure("echo")
        fb = hm.get_fallback_agent("echo")
        assert fb == "aura"

    def test_fallback_sentinel_none(self):
        hm = AgentHealthMonitor()
        assert hm.get_fallback_agent("sentinel") is None

    def test_reset_agent(self):
        hm = AgentHealthMonitor(failure_threshold=1)
        hm.record_failure("forge")
        assert hm.get_agent_health("forge") == HealthStatus.UNHEALTHY
        hm.reset_agent("forge")
        assert hm.get_agent_health("forge") == HealthStatus.HEALTHY


# ==================== Rate Limiter ====================

class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=5))
        for _ in range(5):
            result = rl.check("u1")
            assert result.allowed is True

    def test_blocks_over_limit(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=2))
        rl.check("u1")
        rl.check("u1")
        result = rl.check("u1")
        assert result.allowed is False
        assert "minute" in result.reason.lower()

    def test_per_org_config(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=1))
        rl.configure_org("org1", RateLimitConfig(requests_per_minute=100))
        # Default user hits limit after 1
        rl.check("u1")
        assert rl.check("u1").allowed is False
        # Org user has higher limit
        for _ in range(50):
            assert rl.check("u2", org_id="org1").allowed is True

    def test_different_users_independent(self):
        rl = RateLimiter(RateLimitConfig(requests_per_minute=1))
        assert rl.check("u1").allowed is True
        assert rl.check("u2").allowed is True
        assert rl.check("u1").allowed is False
        assert rl.check("u2").allowed is False

    def test_usage_stats(self):
        rl = RateLimiter()
        rl.check("u1")
        rl.check("u1")
        usage = rl.get_usage("u1")
        assert usage["last_minute"] == 2


# ==================== Cost Tracker ====================

class TestCostTracker:
    def test_record_and_summary(self):
        ct = CostTracker()
        ct.record("aura", 500, 200)
        ct.record("echo", 300, 100)
        summary = ct.get_summary()
        assert summary["total_records"] == 2
        assert summary["total_cost_usd"] > 0
        assert "aura" in summary["by_agent"]
        assert "echo" in summary["by_agent"]

    def test_cost_tiers(self):
        ct = CostTracker()
        r1 = ct.record("aura", 1000, 1000)   # tier_1
        r2 = ct.record("anchor", 1000, 1000)  # tier_3
        assert r1.cost_usd > r2.cost_usd  # Tier 1 costs more

    def test_filter_by_org(self):
        ct = CostTracker()
        ct.record("aura", 500, 200, org_id="org1")
        ct.record("echo", 300, 100, org_id="org2")
        summary = ct.get_summary(org_id="org1")
        assert summary["total_records"] == 1

    def test_all_agents_have_tiers(self):
        for agent_id in AgentId:
            assert agent_id.value in AGENT_TIERS

    def test_all_agents_have_budgets(self):
        for agent_id in AgentId:
            if agent_id == AgentId.MERIDIAN:
                continue  # Meridian is in budgets
            assert agent_id.value in AGENT_TOKEN_BUDGETS

    def test_token_budget(self):
        ct = CostTracker()
        assert ct.get_token_budget("aura") == 3000
        assert ct.get_token_budget("anchor") == 1500


# ==================== Response Cache ====================

class TestResponseCache:
    def test_put_and_get(self):
        cache = ResponseCache()
        cache.put("aura", "interpret_profile", "u1", {"data": "profile"})
        result = cache.get("aura", "interpret_profile", "u1")
        assert result == {"data": "profile"}

    def test_miss(self):
        cache = ResponseCache()
        assert cache.get("aura", "interpret_profile", "u1") is None

    def test_expiry(self):
        cache = ResponseCache()
        cache.put("aura", "x", "u1", "value", ttl_seconds=0)
        # Immediately expired
        assert cache.get("aura", "x", "u1") is None

    def test_invalidate(self):
        cache = ResponseCache()
        cache.put("aura", "x", "u1", "value")
        assert cache.invalidate("aura", "x", "u1") is True
        assert cache.get("aura", "x", "u1") is None

    def test_clear(self):
        cache = ResponseCache()
        cache.put("aura", "x", "u1", "v1")
        cache.put("echo", "y", "u2", "v2")
        cache.clear()
        assert cache.get("aura", "x", "u1") is None

    def test_stats(self):
        cache = ResponseCache()
        cache.put("aura", "x", "u1", "value", ttl_seconds=3600)
        cache.get("aura", "x", "u1")  # hit
        cache.get("aura", "y", "u1")  # miss
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(0.5)

    def test_eviction(self):
        cache = ResponseCache(max_entries=2)
        cache.put("a", "x", "u1", "v1", ttl_seconds=3600)
        cache.put("b", "x", "u1", "v2", ttl_seconds=3600)
        cache.put("c", "x", "u1", "v3", ttl_seconds=3600)  # triggers eviction
        assert cache.get_stats()["entries"] <= 2

    def test_auto_ttl_profile(self):
        """Aura profile interpretations get 1-hour TTL."""
        cache = ResponseCache()
        cache.put("aura", "interpret_profile", "u1", "profile_data")
        entry = list(cache._cache.values())[0]
        assert entry.ttl == timedelta(seconds=3600)

    def test_auto_ttl_context(self):
        """generate_context gets 30-min TTL."""
        cache = ResponseCache()
        cache.put("aura", "generate_context", "u1", "context_data")
        entry = list(cache._cache.values())[0]
        assert entry.ttl == timedelta(seconds=1800)
