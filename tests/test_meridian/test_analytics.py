from __future__ import annotations
import pytest
from ai.meridian.analytics.dashboard import AgentAnalytics


class TestAgentAnalytics:
    def test_record_and_count(self):
        a = AgentAnalytics()
        a.record_usage("aura", "interpret_profile", "u1", "s1", confidence=0.88, status="completed")
        a.record_usage("nova", "career_strategy", "u1", "s1", confidence=0.82, status="completed")
        assert a.get_record_count() == 2

    def test_metrics_per_agent(self):
        a = AgentAnalytics()
        a.record_usage("aura", "interpret_profile", "u1", "s1", confidence=0.9, status="completed")
        a.record_usage("aura", "deep_dive", "u2", "s2", confidence=0.8, status="completed")
        a.record_usage("aura", "interpret_profile", "u3", "s3", confidence=0.0, status="failed")

        metrics = a.get_agent_metrics("aura")
        assert len(metrics) == 1
        m = metrics[0]
        assert m.total_invocations == 3
        assert m.successful == 2
        assert m.failed == 1
        assert m.avg_confidence == pytest.approx(0.85, abs=0.01)
        assert m.action_breakdown["interpret_profile"] == 2
        assert m.action_breakdown["deep_dive"] == 1

    def test_metrics_filter(self):
        a = AgentAnalytics()
        a.record_usage("aura", "x", "u1", "s1")
        a.record_usage("nova", "y", "u1", "s1")
        assert len(a.get_agent_metrics("aura")) == 1
        assert len(a.get_agent_metrics()) == 2

    def test_dashboard_summary(self):
        a = AgentAnalytics()
        a.record_usage("aura", "x", "u1", "s1", status="completed")
        a.record_usage("nova", "y", "u1", "s1", status="failed")
        summary = a.get_dashboard_summary()
        assert summary["total_invocations"] == 2
        assert summary["total_successful"] == 1
        assert summary["success_rate"] == pytest.approx(0.5)
        assert summary["active_agents"] == 2

    def test_ratings(self):
        a = AgentAnalytics()
        a.record_usage("aura", "x", "u1", "s1", rating=5)
        a.record_usage("aura", "x", "u2", "s2", rating=3)
        m = a.get_agent_metrics("aura")[0]
        assert m.avg_rating == pytest.approx(4.0)

    def test_empty_dashboard(self):
        summary = AgentAnalytics().get_dashboard_summary()
        assert summary["total_invocations"] == 0
        assert summary["success_rate"] == 0.0
