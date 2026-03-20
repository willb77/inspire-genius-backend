from __future__ import annotations

"""Tests for BaseOrchestrator — domain orchestrator base class."""

import pytest
from unittest.mock import patch, AsyncMock

from ai.meridian.core.types import (
    AgentTask,
    AgentResult,
    AgentCapability,
    AgentId,
    OrchestratorId,
    TaskStatus,
    ConfidenceLevel,
    DAGNode,
    ProcessTemplate,
)
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.orchestrator import BaseOrchestrator


# ---------------------------------------------------------------------------
# Concrete subclasses for testing
# ---------------------------------------------------------------------------

class _StubAgent(BaseAgent):
    def __init__(self, agent_id: AgentId = AgentId.ECHO):
        super().__init__(agent_id)

    async def process_task(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            task_id=task.task_id,
            agent_id=self._agent_id,
            status=TaskStatus.COMPLETED,
            output={"done": True, "action": task.action},
            confidence=0.9,
        )

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=self._agent_id,
            name="Stub",
            tagline="Test stub",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=["test"],
            description="Stub agent",
        )


class _StubOrchestrator(BaseOrchestrator):
    """Minimal concrete orchestrator."""

    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        return []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegisterAndGetAgent:

    @patch("ai.meridian.core.orchestrator.logger")
    def test_register_agent(self, mock_logger):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        agent = _StubAgent(AgentId.ECHO)

        orch.register_agent(agent)

        assert orch.get_agent(AgentId.ECHO) is agent
        mock_logger.info.assert_called_once()

    def test_get_agent_returns_none_for_unknown(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        assert orch.get_agent(AgentId.FORGE) is None


class TestRegisterAndMatchTemplate:

    def test_register_and_match(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        tpl = ProcessTemplate(
            template_id="tpl_1",
            name="Burnout Assessment",
            description="Assess burnout risk",
            trigger_patterns=["burnout", "stressed out"],
            steps=[{"agent": "echo", "action": "assess"}],
        )
        orch.register_template(tpl)

        matched = orch.match_template("I'm feeling burnout")
        assert matched is not None
        assert matched.template_id == "tpl_1"

    def test_match_template_case_insensitive(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        tpl = ProcessTemplate(
            template_id="tpl_2",
            name="Conflict",
            description="Resolve conflict",
            trigger_patterns=["conflict resolution"],
            steps=[],
        )
        orch.register_template(tpl)

        assert orch.match_template("CONFLICT RESOLUTION needed") is not None

    def test_match_template_returns_none(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        assert orch.match_template("unrelated topic") is None


class TestExecuteDAG:

    @pytest.mark.asyncio
    @patch("ai.meridian.core.orchestrator.logger")
    @patch("ai.meridian.core.base_agent.logger")
    async def test_simple_two_node_dag(self, mock_agent_logger, mock_orch_logger):
        """Node B depends on Node A — both should complete in order."""
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        agent_echo = _StubAgent(AgentId.ECHO)
        agent_forge = _StubAgent(AgentId.FORGE)
        orch.register_agent(agent_echo)
        orch.register_agent(agent_forge)

        node_a = DAGNode(
            node_id="a",
            task=AgentTask(agent_id=AgentId.ECHO, action="step_1"),
            dependencies=[],
        )
        node_b = DAGNode(
            node_id="b",
            task=AgentTask(agent_id=AgentId.FORGE, action="step_2"),
            dependencies=["a"],
        )

        results = await orch.execute_dag([node_a, node_b])

        assert len(results) == 2
        assert results[0].agent_id == AgentId.ECHO
        assert results[0].status == TaskStatus.COMPLETED
        assert results[1].agent_id == AgentId.FORGE
        assert results[1].status == TaskStatus.COMPLETED
        # Node B should have dependency_results injected
        assert "dependency_results" in node_b.task.context
        assert "a" in node_b.task.context["dependency_results"]

    @pytest.mark.asyncio
    @patch("ai.meridian.core.orchestrator.logger")
    async def test_missing_agent_returns_failed(self, mock_logger):
        """If no agent is registered, execute_dag returns a FAILED result."""
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        # Do NOT register any agent

        node = DAGNode(
            node_id="x",
            task=AgentTask(agent_id=AgentId.NOVA, action="hire"),
            dependencies=[],
        )

        results = await orch.execute_dag([node])

        assert len(results) == 1
        assert results[0].status == TaskStatus.FAILED
        assert results[0].output["error"] == "Agent not registered"


class TestCheckConfidence:

    def test_high(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        assert orch._check_confidence(0.85) == ConfidenceLevel.HIGH
        assert orch._check_confidence(1.0) == ConfidenceLevel.HIGH

    def test_medium(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        assert orch._check_confidence(0.60) == ConfidenceLevel.MEDIUM
        assert orch._check_confidence(0.84) == ConfidenceLevel.MEDIUM

    def test_low(self):
        orch = _StubOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        assert orch._check_confidence(0.59) == ConfidenceLevel.LOW
        assert orch._check_confidence(0.0) == ConfidenceLevel.LOW
