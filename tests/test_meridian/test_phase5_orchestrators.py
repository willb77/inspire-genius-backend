from __future__ import annotations

"""Tests for Phase 5 orchestrators, RLHF pipeline, and full service integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai.meridian.core.types import AgentId, AgentTask, OrchestratorId, TaskStatus
from ai.meridian.agents.org_intel.org_intel_orchestrator import OrgIntelOrchestrator
from ai.meridian.agents.triage.triage_orchestrator import HiringTriageOrchestrator
from ai.meridian.agents.atlas.atlas_agent import AtlasAgent
from ai.meridian.agents.sentinel.sentinel_agent import SentinelAgent
from ai.meridian.agents.nexus.nexus_agent import NexusAgent
from ai.meridian.agents.bridge.bridge_agent import BridgeAgent
from ai.meridian.agents.sage.sage_agent import SageAgent
from ai.meridian.agents.ascend.ascend_agent import AscendAgent
from ai.meridian.agents.alex.alex_agent import AlexAgent
from ai.meridian.agents.nova.nova_agent import NovaAgent
from ai.meridian.agents.james.james_agent import JamesAgent
from ai.meridian.feedback.feedback_service import FeedbackService
from ai.meridian.api.service import MeridianService
from ai.meridian.memory.memory_service import MemoryService


# ==================== OrgIntel Orchestrator ====================

class TestOrgIntelOrchestrator:
    def _make(self):
        orch = OrgIntelOrchestrator()
        orch.register_agent(AtlasAgent())
        orch.register_agent(SentinelAgent())
        orch.register_agent(NexusAgent())
        orch.register_agent(BridgeAgent())
        return orch

    @pytest.mark.asyncio
    async def test_compliance_routes_to_sentinel(self):
        dag = await self._make().plan("Check GDPR compliance for this report", {"user_id": "u1"})
        assert dag[0].task.agent_id == AgentId.SENTINEL

    @pytest.mark.asyncio
    async def test_pipeline_routes_to_bridge(self):
        dag = await self._make().plan("Show me the talent pipeline health", {"user_id": "u1"})
        assert dag[0].task.agent_id == AgentId.BRIDGE

    @pytest.mark.asyncio
    async def test_culture_routes_to_nexus(self):
        dag = await self._make().plan("Tell me about Japanese cultural norms", {"user_id": "u1"})
        assert dag[0].task.agent_id == AgentId.NEXUS

    @pytest.mark.asyncio
    async def test_team_routes_to_atlas(self):
        dag = await self._make().plan("Analyze my team composition", {"user_id": "u1"})
        assert dag[0].task.agent_id == AgentId.ATLAS

    @pytest.mark.asyncio
    async def test_default_routes_to_atlas(self):
        dag = await self._make().plan("hello", {"user_id": "u1"})
        assert dag[0].task.agent_id == AgentId.ATLAS


# ==================== Strategic Advisory with new agents ====================

class TestStrategicAdvisoryExpanded:
    def _make(self):
        orch = HiringTriageOrchestrator()
        orch.register_agent(NovaAgent())
        orch.register_agent(JamesAgent())
        orch.register_agent(SageAgent())
        orch.register_agent(AscendAgent())
        orch.register_agent(AlexAgent())
        return orch

    @pytest.mark.asyncio
    async def test_research_routes_to_sage(self):
        dag = await self._make().plan("Synthesize research on team dynamics", {"user_id": "u1", "parameters": {}})
        assert dag[0].task.agent_id == AgentId.SAGE

    @pytest.mark.asyncio
    async def test_leadership_routes_to_ascend(self):
        dag = await self._make().plan("Help me develop my leadership skills", {"user_id": "u1", "parameters": {}})
        assert dag[0].task.agent_id == AgentId.ASCEND

    @pytest.mark.asyncio
    async def test_student_routes_to_alex(self):
        dag = await self._make().plan("I'm a student exploring career options", {"user_id": "u1", "parameters": {}})
        assert dag[0].task.agent_id == AgentId.ALEX

    @pytest.mark.asyncio
    async def test_career_still_routes_to_nova(self):
        dag = await self._make().plan("Help me plan my career path", {"user_id": "u1", "parameters": {}})
        assert dag[0].task.agent_id == AgentId.NOVA


# ==================== Feedback Service ====================

class TestFeedbackService:
    @pytest.mark.asyncio
    async def test_record_feedback(self):
        memory = MagicMock()
        memory.store_feedback = AsyncMock(return_value="mem-1")
        svc = FeedbackService(memory_service=memory)

        fid = await svc.record_feedback(
            user_id="u1", session_id="s1", agent_id="aura",
            original_response="original", correction="better", rating=4,
        )
        assert fid is not None
        assert svc.get_entry_count() == 1
        memory.store_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_without_correction(self):
        svc = FeedbackService()
        fid = await svc.record_feedback(
            user_id="u1", session_id="s1", agent_id="nova",
            original_response="original", rating=5,
        )
        assert svc.get_entry_count() == 1

    @pytest.mark.asyncio
    async def test_decision_outcome(self):
        svc = FeedbackService()
        fid = await svc.record_feedback(
            user_id="u1", session_id="s1", agent_id="james",
            original_response="original", correction="better",
        )
        assert await svc.record_decision_outcome(fid, "helpful") is True
        assert await svc.record_decision_outcome("nonexistent", "helpful") is False

    @pytest.mark.asyncio
    async def test_stats(self):
        svc = FeedbackService()
        await svc.record_feedback("u1", "s1", "aura", "o1", rating=5)
        await svc.record_feedback("u1", "s1", "aura", "o2", correction="c", rating=3)
        await svc.record_feedback("u1", "s1", "nova", "o3", rating=4)

        stats = svc.get_stats()
        assert stats.total_feedback == 3
        assert stats.total_corrections == 1
        assert stats.avg_rating == pytest.approx(4.0)

        aura_stats = svc.get_stats("aura")
        assert aura_stats.total_feedback == 2

    @pytest.mark.asyncio
    async def test_export_training_data(self):
        svc = FeedbackService()
        await svc.record_feedback("u1", "s1", "aura", "orig", correction="fix", rating=4)
        await svc.record_feedback("u1", "s1", "nova", "orig2")  # no correction

        data = svc.export_training_data()
        assert len(data) == 1
        assert data[0]["correction"] == "fix"


# ==================== Full MeridianService ====================

class TestMeridianServiceFull:
    def _make(self):
        memory = MagicMock(spec=MemoryService)
        memory.get_behavioral_profile = AsyncMock(return_value=None)
        memory.cache_behavioral_profile = AsyncMock()
        memory.store_feedback = AsyncMock(return_value="fb-1")
        memory.store = AsyncMock(return_value="e-1")
        return MeridianService(memory_service=memory)

    def test_all_13_agents_registered(self):
        svc = self._make()
        agents = svc.list_agent_capabilities()
        agent_ids = {a["agent_id"] for a in agents}
        expected = {
            "aura", "echo", "anchor", "forge",  # Personal Development
            "atlas", "sentinel", "nexus", "bridge",  # Org Intelligence
            "nova", "james", "sage", "ascend", "alex",  # Strategic Advisory
        }
        assert expected.issubset(agent_ids), f"Missing: {expected - agent_ids}"

    def test_all_3_orchestrators(self):
        svc = self._make()
        assert OrchestratorId.PERSONAL_DEVELOPMENT in svc._orchestrators
        assert OrchestratorId.STRATEGIC_ADVISORY in svc._orchestrators
        assert OrchestratorId.ORGANIZATIONAL_INTELLIGENCE in svc._orchestrators

    @pytest.mark.asyncio
    async def test_chat_routes_org_intel(self):
        svc = self._make()
        result = await svc.chat("u1", "s1", "Analyze my team composition diversity")
        assert "response" in result

    @pytest.mark.asyncio
    async def test_rlhf_feedback(self):
        svc = self._make()
        fid = await svc.record_rlhf_feedback(
            user_id="u1", session_id="s1", agent_id="aura",
            original_response="orig", correction="better", rating=4,
        )
        assert fid is not None

    def test_feedback_stats(self):
        svc = self._make()
        stats = svc.get_feedback_stats()
        assert stats["total_feedback"] == 0

    def test_export_training(self):
        svc = self._make()
        data = svc.export_training_data()
        assert isinstance(data, list)

    def test_analytics_summary(self):
        svc = self._make()
        summary = svc.get_analytics_summary()
        assert "total_invocations" in summary
