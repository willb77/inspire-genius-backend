from __future__ import annotations
import pytest
from ai.meridian.agents.anchor.anchor_agent import AnchorAgent
from ai.meridian.agents.anchor.anchor_tools import (
    EnergyLevel, assess_burnout_risk, build_recovery_protocol,
)
from ai.meridian.core.types import AgentId, AgentTask, OrchestratorId, TaskStatus


class TestAnchorCapabilities:
    def test_id(self):
        assert AnchorAgent().agent_id == AgentId.ANCHOR

    def test_capabilities(self):
        cap = AnchorAgent().get_capabilities()
        assert cap.domain == OrchestratorId.PERSONAL_DEVELOPMENT
        assert "stress_checkin" in cap.actions

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        r = await AnchorAgent().process_task(AgentTask(agent_id=AgentId.ANCHOR, action="nope", parameters={}))
        assert r.status == TaskStatus.FAILED


class TestStressCheckin:
    @pytest.mark.asyncio
    async def test_moderate_stress(self):
        r = await AnchorAgent().process_task(AgentTask(
            agent_id=AgentId.ANCHOR, action="stress_checkin",
            parameters={"user_id": "u1", "stress_score": 5, "energy_level": "moderate"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert r.output["is_private"] is True
        assert r.output["assessment"]["risk_level"] in ("low", "moderate")

    @pytest.mark.asyncio
    async def test_high_stress_escalation(self):
        r = await AnchorAgent().process_task(AgentTask(
            agent_id=AgentId.ANCHOR, action="stress_checkin",
            parameters={"user_id": "u1", "stress_score": 9, "energy_level": "critical"},
        ))
        assert r.status == TaskStatus.AWAITING_HUMAN
        assert r.output["assessment"]["needs_escalation"] is True

    @pytest.mark.asyncio
    async def test_all_outputs_private(self):
        """Every Anchor output must have is_private=True."""
        agent = AnchorAgent()
        for action in ["stress_checkin", "recovery_protocol", "resilience_tips"]:
            params = {"user_id": "u1", "stress_score": 5, "energy_level": "moderate"}
            if action == "recovery_protocol":
                params["risk_level"] = "moderate"
            r = await agent.process_task(AgentTask(
                agent_id=AgentId.ANCHOR, action=action, parameters=params,
                behavioral_context={"primary_preference": "green"},
            ))
            assert r.output.get("is_private") is True, f"{action} missing is_private"


class TestRecoveryProtocol:
    @pytest.mark.asyncio
    async def test_high_priority(self):
        r = await AnchorAgent().process_task(AgentTask(
            agent_id=AgentId.ANCHOR, action="recovery_protocol",
            parameters={"risk_level": "high"},
            behavioral_context={"primary_preference": "red"},
        ))
        assert r.status == TaskStatus.COMPLETED
        protocol = r.output["protocol"]
        assert "permission to rest" in protocol["behavioral_adaptation"].lower()


class TestResilienceTips:
    @pytest.mark.asyncio
    async def test_tips_with_context(self):
        r = await AnchorAgent().process_task(AgentTask(
            agent_id=AgentId.ANCHOR, action="resilience_tips",
            parameters={},
            behavioral_context={"primary_preference": "blue"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert len(r.output["tips"]) >= 1


class TestAnchorTools:
    def test_burnout_low_risk(self):
        a = assess_burnout_risk(3, EnergyLevel.GOOD)
        assert a["risk_level"] == "low"
        assert a["needs_escalation"] is False

    def test_burnout_high_risk(self):
        a = assess_burnout_risk(9, EnergyLevel.CRITICAL)
        assert a["risk_level"] == "high"
        assert a["needs_escalation"] is True

    def test_trending_worse(self):
        a = assess_burnout_risk(5, EnergyLevel.MODERATE, [3, 4, 5])
        assert a["trending_worse"] is True

    def test_recovery_protocol_adaptation(self):
        p = build_recovery_protocol("high", {"primary_preference": "green"})
        assert any("connect" in s.lower() or "friend" in s.lower() or "colleague" in s.lower() for s in p.steps)
