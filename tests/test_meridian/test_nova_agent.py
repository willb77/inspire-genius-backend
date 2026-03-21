from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai.meridian.agents.nova.nova_agent import NovaAgent
from ai.meridian.agents.nova.nova_tools import (
    CandidateSubmission,
    CandidateTier,
    CareerPathway,
    TriageResult,
    build_career_pathways,
    aggregate_triage_dashboard,
)
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentCapability, OrchestratorId, TaskStatus,
)


def _make_agent(memory=None):
    return NovaAgent(memory_service=memory)


class TestNovaCapabilities:
    def test_agent_id(self):
        assert _make_agent().agent_id == AgentId.NOVA

    def test_capabilities(self):
        cap = _make_agent().get_capabilities()
        assert cap.domain == OrchestratorId.STRATEGIC_ADVISORY
        assert "career_strategy" in cap.actions
        assert "submit_candidate" in cap.actions

    def test_unknown_action(self):
        @pytest.fixture
        def _():
            pass

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        result = await _make_agent().process_task(
            AgentTask(agent_id=AgentId.NOVA, action="nope", parameters={})
        )
        assert result.status == TaskStatus.FAILED


class TestCareerStrategy:
    @pytest.mark.asyncio
    async def test_with_behavioral_context(self):
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="career_strategy",
            parameters={},
            behavioral_context={
                "primary_preference": "blue",
                "secondary_preference": "red",
            },
        )
        result = await _make_agent().process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert "pathways" in result.output
        assert len(result.output["pathways"]) > 0

    @pytest.mark.asyncio
    async def test_without_behavioral_context(self):
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="career_strategy",
            parameters={},
            behavioral_context=None,
        )
        result = await _make_agent().process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert "pathways" in result.output


class TestSubmitCandidate:
    @pytest.mark.asyncio
    async def test_submit_stores_in_pipeline(self):
        memory = MagicMock()
        memory.store = AsyncMock(return_value="e1")
        agent = _make_agent(memory=memory)

        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="submit_candidate",
            parameters={
                "name": "Alice",
                "email": "alice@example.com",
                "job_blueprint_id": "bp-1",
                "skills": ["python", "sql"],
                "experience_years": 5,
            },
            context={"session_id": "s1"},
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.output["status"] == "prism_light_triggered"
        assert result.output["job_blueprint_id"] == "bp-1"
        assert len(agent.get_pipeline("bp-1")) == 1
        memory.store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_submit_missing_blueprint_id(self):
        result = await _make_agent().process_task(
            AgentTask(
                agent_id=AgentId.NOVA,
                action="submit_candidate",
                parameters={"name": "Bob"},
            )
        )
        assert result.status == TaskStatus.FAILED


class TestPublishTriage:
    @pytest.mark.asyncio
    async def test_publish_aggregates(self):
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="publish_triage",
            parameters={
                "job_blueprint_id": "bp-1",
                "job_title": "Engineer",
                "triage_results": [
                    {"candidate_id": "c1", "tier": "strong_fit", "fit_score": 0.85},
                    {"candidate_id": "c2", "tier": "potential_fit", "fit_score": 0.65},
                    {"candidate_id": "c3", "tier": "misalignment_detected", "fit_score": 0.3},
                ],
            },
        )
        result = await _make_agent().process_task(task)
        assert result.status == TaskStatus.COMPLETED
        dash = result.output["dashboard"]
        assert dash["strong_fit_count"] == 1
        assert dash["potential_fit_count"] == 1
        assert dash["misalignment_count"] == 1
        assert dash["total_candidates"] == 3


class TestPromotionReadiness:
    @pytest.mark.asyncio
    async def test_with_context(self):
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="promotion_readiness",
            parameters={"target_role": "Senior Engineer"},
            behavioral_context={"primary_preference": "blue", "insights": ["analytical"]},
        )
        result = await _make_agent().process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert "Senior Engineer" in result.output.get("summary", "")

    @pytest.mark.asyncio
    async def test_without_context(self):
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="promotion_readiness",
            parameters={"target_role": "Manager"},
            behavioral_context=None,
        )
        result = await _make_agent().process_task(task)
        assert result.output.get("readiness_score") is None


class TestNovaTools:
    def test_build_pathways_with_context(self):
        paths = build_career_pathways({"primary_preference": "green", "secondary_preference": "blue"})
        assert len(paths) >= 1
        assert any("People" in p.title or "Client" in p.title for p in paths)

    def test_build_pathways_without_context(self):
        paths = build_career_pathways(None)
        assert len(paths) == 1
        assert "Exploration" in paths[0].title

    def test_aggregate_dashboard(self):
        results = [
            TriageResult(candidate_id="c1", job_blueprint_id="bp", tier=CandidateTier.STRONG_FIT, fit_score=0.9),
            TriageResult(candidate_id="c2", job_blueprint_id="bp", tier=CandidateTier.PENDING, fit_score=0.0),
        ]
        dash = aggregate_triage_dashboard("bp", "Role", results)
        assert dash.total_candidates == 2
        assert dash.strong_fit_count == 1
        assert dash.pending_count == 1
