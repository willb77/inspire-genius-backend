from __future__ import annotations
import pytest
from ai.meridian.agents.forge.forge_agent import ForgeAgent
from ai.meridian.agents.forge.forge_tools import (
    analyze_conflict, build_communication_playbook, build_meeting_briefing,
)
from ai.meridian.core.types import AgentId, AgentTask, OrchestratorId, TaskStatus


class TestForgeCapabilities:
    def test_id(self):
        assert ForgeAgent().agent_id == AgentId.FORGE

    def test_capabilities(self):
        cap = ForgeAgent().get_capabilities()
        assert cap.domain == OrchestratorId.PERSONAL_DEVELOPMENT
        assert "resolve_conflict" in cap.actions
        assert "communication_playbook" in cap.actions
        assert "meeting_briefing" in cap.actions

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        r = await ForgeAgent().process_task(AgentTask(agent_id=AgentId.FORGE, action="nope", parameters={}))
        assert r.status == TaskStatus.FAILED


class TestConflictResolution:
    @pytest.mark.asyncio
    async def test_resolve_with_both_profiles(self):
        r = await ForgeAgent().process_task(AgentTask(
            agent_id=AgentId.FORGE, action="resolve_conflict",
            parameters={
                "situation": "disagreement about project timeline",
                "counterpart_context": {"primary_preference": "red"},
            },
            behavioral_context={"primary_preference": "gold"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert "analysis" in r.output
        assert len(r.output["analysis"]["friction_points"]) > 0

    @pytest.mark.asyncio
    async def test_resolve_without_counterpart(self):
        r = await ForgeAgent().process_task(AgentTask(
            agent_id=AgentId.FORGE, action="resolve_conflict",
            parameters={"situation": "general tension"},
        ))
        assert r.status == TaskStatus.COMPLETED


class TestCommunicationPlaybook:
    @pytest.mark.asyncio
    async def test_playbook(self):
        r = await ForgeAgent().process_task(AgentTask(
            agent_id=AgentId.FORGE, action="communication_playbook",
            parameters={
                "situation": "asking for a raise",
                "counterpart_context": {"primary_preference": "blue"},
            },
            behavioral_context={"primary_preference": "green"},
        ))
        assert r.status == TaskStatus.COMPLETED
        pb = r.output["playbook"]
        assert len(pb["opening_scripts"]) > 0
        assert len(pb["phrases_to_avoid"]) > 0


class TestMeetingBriefing:
    @pytest.mark.asyncio
    async def test_briefing(self):
        r = await ForgeAgent().process_task(AgentTask(
            agent_id=AgentId.FORGE, action="meeting_briefing",
            parameters={
                "meeting_purpose": "quarterly review",
                "attendees": [
                    {"name": "Alice", "primary_preference": "gold"},
                    {"name": "Bob", "primary_preference": "red"},
                ],
            },
        ))
        assert r.status == TaskStatus.COMPLETED
        b = r.output["briefing"]
        assert len(b["attendee_insights"]) == 2


class TestForgeTools:
    def test_conflict_gold_red(self):
        a = analyze_conflict(
            {"primary_preference": "gold"}, {"primary_preference": "red"}, "timeline dispute",
        )
        assert len(a.friction_points) > 0
        assert len(a.common_ground) > 0

    def test_playbook_adapts_to_counterpart(self):
        pb = build_communication_playbook(
            "salary negotiation",
            {"primary_preference": "green"},
            {"primary_preference": "blue"},
        )
        assert any("data" in s.lower() or "evidence" in s.lower() for s in pb.opening_scripts)

    def test_meeting_briefing_multiple(self):
        b = build_meeting_briefing("standup", [
            {"name": "A", "primary_preference": "gold"},
            {"name": "B", "primary_preference": "green"},
            {"name": "C", "primary_preference": "blue"},
        ])
        assert len(b.attendee_insights) == 3
