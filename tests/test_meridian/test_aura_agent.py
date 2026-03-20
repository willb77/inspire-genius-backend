from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai.meridian.agents.aura.aura_agent import AuraAgent
from ai.meridian.agents.aura.aura_tools import (
    PRISMDimensions,
    BehavioralPreferenceMap,
    PRISMProfileRetriever,
    analyze_dimensions,
)
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PRISM_DATA = {
    "dimensions": {"gold": 72, "green": 85, "blue": 58, "red": 63},
    "assessed_at": "2026-03-15T10:00:00Z",
}


def _make_agent(memory=None, retriever=None):
    return AuraAgent(
        llm_provider=None,
        memory_service=memory,
        prism_retriever=retriever,
    )


# ---------------------------------------------------------------------------
# Tests: capabilities & identity
# ---------------------------------------------------------------------------

class TestAuraCapabilities:
    def test_agent_id_is_aura(self):
        agent = _make_agent()
        assert agent.agent_id == AgentId.AURA

    def test_get_capabilities(self):
        cap = _make_agent().get_capabilities()
        assert isinstance(cap, AgentCapability)
        assert cap.agent_id == AgentId.AURA
        assert cap.domain == OrchestratorId.PERSONAL_DEVELOPMENT
        assert "interpret_profile" in cap.actions
        assert "deep_dive" in cap.actions
        assert "track_growth" in cap.actions
        assert "generate_context" in cap.actions

    def test_report_status(self):
        status = _make_agent().report_status()
        assert status["agent_id"] == "aura"
        assert status["is_active"] is True


# ---------------------------------------------------------------------------
# Tests: interpret_profile
# ---------------------------------------------------------------------------

class TestInterpretProfile:
    @pytest.mark.asyncio
    async def test_interpret_with_prism_data(self):
        memory = MagicMock()
        memory.cache_behavioral_profile = AsyncMock()
        agent = _make_agent(memory=memory)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="interpret_profile",
            parameters={"user_id": "u1", "prism_data": SAMPLE_PRISM_DATA},
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.output["has_profile"] is True
        assert "behavioral_preference_map" in result.output
        bpm = result.output["behavioral_preference_map"]
        assert bpm["dimensions"]["green"] == 85
        assert bpm["primary_preference"] == "green"
        memory.cache_behavioral_profile.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_interpret_no_profile(self):
        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_profile = AsyncMock(return_value=None)
        agent = _make_agent(retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="interpret_profile",
            parameters={"user_id": "u1"},
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert result.output["has_profile"] is False

    @pytest.mark.asyncio
    async def test_interpret_missing_user_id(self):
        agent = _make_agent()
        task = AgentTask(
            agent_id=AgentId.AURA,
            action="interpret_profile",
            parameters={},
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.FAILED
        assert "user_id" in result.output.get("error", "")


# ---------------------------------------------------------------------------
# Tests: deep_dive
# ---------------------------------------------------------------------------

class TestDeepDive:
    @pytest.mark.asyncio
    async def test_deep_dive_with_profile(self):
        memory = MagicMock()
        memory.get_behavioral_profile = AsyncMock(return_value=None)
        memory.cache_behavioral_profile = AsyncMock()

        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_profile = AsyncMock(
            return_value=BehavioralPreferenceMap(
                user_id="u1",
                dimensions=PRISMDimensions(**SAMPLE_PRISM_DATA["dimensions"]),
                primary_preference="green",
                secondary_preference="gold",
            )
        )
        agent = _make_agent(memory=memory, retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="deep_dive",
            parameters={"user_id": "u1", "dimension": "green"},
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "analysis" in result.output
        assert result.output["analysis"]["focus"] == "green"

    @pytest.mark.asyncio
    async def test_deep_dive_no_profile(self):
        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_profile = AsyncMock(return_value=None)
        agent = _make_agent(retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="deep_dive",
            parameters={"user_id": "u1"},
        )
        result = await agent.process_task(task)
        assert result.output["has_profile"] is False


# ---------------------------------------------------------------------------
# Tests: track_growth
# ---------------------------------------------------------------------------

class TestTrackGrowth:
    @pytest.mark.asyncio
    async def test_track_growth_insufficient_history(self):
        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_assessment_history = AsyncMock(return_value=[])
        agent = _make_agent(retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="track_growth",
            parameters={"user_id": "u1"},
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert result.output["assessments_available"] == 0

    @pytest.mark.asyncio
    async def test_track_growth_with_history(self):
        prev = BehavioralPreferenceMap(
            user_id="u1",
            dimensions=PRISMDimensions(gold=60, green=70, blue=50, red=55),
            primary_preference="green",
            secondary_preference="gold",
        )
        curr = BehavioralPreferenceMap(
            user_id="u1",
            dimensions=PRISMDimensions(gold=65, green=75, blue=52, red=55),
            primary_preference="green",
            secondary_preference="gold",
        )
        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_assessment_history = AsyncMock(return_value=[curr, prev])
        agent = _make_agent(retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="track_growth",
            parameters={"user_id": "u1"},
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert "growth_analysis" in result.output
        changes = result.output["growth_analysis"]["changes"]
        assert changes["gold"]["delta"] == 5
        assert changes["green"]["delta"] == 5
        assert changes["red"]["delta"] == 0


# ---------------------------------------------------------------------------
# Tests: generate_context
# ---------------------------------------------------------------------------

class TestGenerateContext:
    @pytest.mark.asyncio
    async def test_generate_context_with_profile(self):
        memory = MagicMock()
        memory.get_behavioral_profile = AsyncMock(return_value=None)
        memory.cache_behavioral_profile = AsyncMock()

        retriever = MagicMock(spec=PRISMProfileRetriever)
        retriever.get_profile = AsyncMock(
            return_value=BehavioralPreferenceMap(
                user_id="u1",
                dimensions=PRISMDimensions(gold=72, green=85, blue=58, red=63),
                primary_preference="green",
                secondary_preference="gold",
            )
        )
        agent = _make_agent(memory=memory, retriever=retriever)

        task = AgentTask(
            agent_id=AgentId.AURA,
            action="generate_context",
            parameters={"user_id": "u1", "requesting_agent": "nova"},
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert result.output["has_profile"] is True
        ctx = result.output["behavioral_context"]
        assert ctx["primary_preference"] == "green"


# ---------------------------------------------------------------------------
# Tests: unknown action
# ---------------------------------------------------------------------------

class TestUnknownAction:
    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        agent = _make_agent()
        task = AgentTask(
            agent_id=AgentId.AURA,
            action="nonexistent",
            parameters={"user_id": "u1"},
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.FAILED


# ---------------------------------------------------------------------------
# Tests: aura_tools helpers
# ---------------------------------------------------------------------------

class TestAnalyzeDimensions:
    def test_analyze_balanced(self):
        dims = PRISMDimensions(gold=55, green=60, blue=50, red=52)
        result = analyze_dimensions(dims)
        assert result["primary"] == "green"
        assert result["secondary"] == "gold"
        assert any("balanced" in i.lower() or "versatil" in i.lower() for i in result["insights"])

    def test_analyze_strong_preference(self):
        dims = PRISMDimensions(gold=30, green=90, blue=40, red=45)
        result = analyze_dimensions(dims)
        assert result["primary"] == "green"
        assert len(result["stress_behaviors"]) > 0
        assert len(result["communication"]) > 0

    def test_growth_areas_for_low_dims(self):
        dims = PRISMDimensions(gold=80, green=75, blue=30, red=25)
        result = analyze_dimensions(dims)
        assert len(result["growth_areas"]) >= 1

    def test_behavioral_preference_map_to_context(self):
        bpm = BehavioralPreferenceMap(
            user_id="u1",
            dimensions=PRISMDimensions(gold=72, green=85, blue=58, red=63),
            primary_preference="green",
            secondary_preference="gold",
            behavioral_insights=["insight 1"],
        )
        ctx = bpm.to_context_dict()
        assert ctx["user_id"] == "u1"
        assert ctx["dimensions"]["green"] == 85
        assert ctx["primary_preference"] == "green"
        assert "insight 1" in ctx["insights"]
