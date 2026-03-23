from __future__ import annotations

"""Tests for BaseAgent — abstract agent base class."""

import pytest
from unittest.mock import patch, MagicMock

from ai.meridian.core.types import (
    AgentTask,
    AgentResult,
    AgentCapability,
    AgentId,
    OrchestratorId,
    TaskStatus,
)
from ai.meridian.core.base_agent import BaseAgent


# ---------------------------------------------------------------------------
# Concrete test subclass
# ---------------------------------------------------------------------------

class _StubAgent(BaseAgent):
    """Minimal concrete implementation for testing."""

    def __init__(
        self,
        agent_id: AgentId = AgentId.ECHO,
        *,
        raise_on_process: Exception | None = None,
    ):
        super().__init__(agent_id)
        self._raise_on_process = raise_on_process

    async def process_task(self, task: AgentTask) -> AgentResult:
        if self._raise_on_process:
            raise self._raise_on_process
        return AgentResult(
            task_id=task.task_id,
            agent_id=self._agent_id,
            status=TaskStatus.COMPLETED,
            output={"echo": task.action},
            confidence=0.9,
            reasoning="Processed successfully",
        )

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=self._agent_id,
            name="Echo",
            tagline="Test echo agent",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=["echo"],
            description="A test agent that echoes tasks",
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBaseAgentAbstract:
    """BaseAgent cannot be instantiated directly."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseAgent(AgentId.ECHO)  # type: ignore[abstract]


class TestStubAgent:
    """Tests using the concrete _StubAgent subclass."""

    @pytest.mark.asyncio
    async def test_process_task_returns_agent_result(self):
        agent = _StubAgent()
        task = AgentTask(agent_id=AgentId.ECHO, action="say_hello")

        result = await agent.process_task(task)

        assert isinstance(result, AgentResult)
        assert result.status == TaskStatus.COMPLETED
        assert result.output == {"echo": "say_hello"}
        assert result.confidence == 0.9

    @pytest.mark.asyncio
    @patch("ai.meridian.core.base_agent.logger")
    async def test_execute_returns_result_on_success(self, mock_logger):
        agent = _StubAgent()
        task = AgentTask(agent_id=AgentId.ECHO, action="ping")

        result = await agent._execute(task)

        assert result.status == TaskStatus.COMPLETED
        assert mock_logger.info.call_count >= 2  # start + completed

    @pytest.mark.asyncio
    @patch("ai.meridian.core.base_agent.logger")
    async def test_execute_returns_failed_on_exception(self, mock_logger):
        agent = _StubAgent(raise_on_process=RuntimeError("boom"))
        task = AgentTask(agent_id=AgentId.ECHO, action="explode")

        result = await agent._execute(task)

        assert result.status == TaskStatus.FAILED
        assert result.confidence == 0.0
        assert "boom" in result.output["error"]
        mock_logger.error.assert_called_once()

    @patch("ai.meridian.core.base_agent.logger")
    def test_inject_behavioral_context_warns_when_none(self, mock_logger):
        agent = _StubAgent()
        task = AgentTask(
            agent_id=AgentId.ECHO,
            action="test",
            behavioral_context=None,
        )

        returned = agent._inject_behavioral_context(task)

        assert returned is task
        mock_logger.warning.assert_called_once()
        assert "without behavioral context" in mock_logger.warning.call_args[0][0]

    @patch("ai.meridian.core.base_agent.logger")
    def test_inject_behavioral_context_no_warn_when_present(self, mock_logger):
        agent = _StubAgent()
        task = AgentTask(
            agent_id=AgentId.ECHO,
            action="test",
            behavioral_context={"style": "direct"},
        )

        agent._inject_behavioral_context(task)

        mock_logger.warning.assert_not_called()

    def test_report_status(self):
        agent = _StubAgent(AgentId.FORGE)
        status = agent.report_status()

        assert status["agent_id"] == "forge"
        assert status["is_active"] is True
        assert "capabilities" in status
        assert status["capabilities"]["agent_id"] == "forge"

    def test_agent_id_property(self):
        agent = _StubAgent(AgentId.ANCHOR)
        assert agent.agent_id == AgentId.ANCHOR
