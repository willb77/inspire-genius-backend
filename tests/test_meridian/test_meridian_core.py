from __future__ import annotations

"""Tests for Meridian — the unified mentor layer."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from ai.meridian.core.types import (
    AgentTask,
    AgentResult,
    AgentId,
    OrchestratorId,
    TaskStatus,
    DAGNode,
    UserIntent,
    ProcessTemplate,
)
from ai.meridian.core.meridian import Meridian
from ai.meridian.core.orchestrator import BaseOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeOrchestrator(BaseOrchestrator):
    """Orchestrator that returns a single completed result."""

    def __init__(self, orch_id: OrchestratorId):
        super().__init__(orch_id)
        self._plan_result: list[DAGNode] = []

    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        return self._plan_result

    def set_plan(self, nodes: list[DAGNode]) -> None:
        self._plan_result = nodes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegisterOrchestrator:

    @patch("ai.meridian.core.meridian.logger")
    def test_register_and_retrieve(self, mock_logger):
        m = Meridian()
        orch = _FakeOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        m.register_orchestrator(orch)

        assert m._orchestrators[OrchestratorId.PERSONAL_DEVELOPMENT] is orch
        mock_logger.info.assert_called_once()


class TestRouteToDomain:

    def test_personal_keywords(self):
        m = Meridian()
        assert m._route_to_domain("help me with my personality") == OrchestratorId.PERSONAL_DEVELOPMENT
        assert m._route_to_domain("dealing with burnout and stress") == OrchestratorId.PERSONAL_DEVELOPMENT

    def test_org_keywords(self):
        m = Meridian()
        assert m._route_to_domain("team compliance audit") == OrchestratorId.ORGANIZATIONAL_INTELLIGENCE

    def test_strategic_keywords(self):
        m = Meridian()
        assert m._route_to_domain("career coaching for leadership") == OrchestratorId.STRATEGIC_ADVISORY

    def test_defaults_to_personal_for_unknown(self):
        m = Meridian()
        assert m._route_to_domain("hello there") == OrchestratorId.PERSONAL_DEVELOPMENT
        assert m._route_to_domain("") == OrchestratorId.PERSONAL_DEVELOPMENT


class TestClassifyIntent:

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    async def test_returns_user_intent(self, mock_logger):
        m = Meridian()
        intent = await m.classify_intent("help me grow", "sess_1")

        assert isinstance(intent, UserIntent)
        assert intent.raw_input == "help me grow"
        assert intent.domain == OrchestratorId.PERSONAL_DEVELOPMENT
        assert intent.intent_type == "general_query"
        assert 0.0 <= intent.confidence <= 1.0

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    @patch("ai.meridian.core.orchestrator.logger")
    async def test_matched_template_populated(self, mock_orch_logger, mock_merid_logger):
        m = Meridian()
        orch = _FakeOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        tpl = ProcessTemplate(
            template_id="tpl_burnout",
            name="Burnout",
            description="Assess burnout",
            trigger_patterns=["burnout"],
            steps=[],
        )
        orch.register_template(tpl)
        m.register_orchestrator(orch)

        intent = await m.classify_intent("I'm experiencing burnout", "sess_2")
        assert intent.matched_template == "tpl_burnout"


class TestProcessMessage:

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    @patch("ai.meridian.core.orchestrator.logger")
    async def test_routes_to_correct_orchestrator(self, mock_orch_logger, mock_merid_logger):
        m = Meridian()
        orch = _FakeOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        m.register_orchestrator(orch)

        response = await m.process_message(
            user_input="help with my personality growth",
            session_id="s1",
            user_id="u1",
        )

        assert isinstance(response, dict)
        assert "response" in response
        assert "intent" in response
        assert "results" in response
        assert response["intent"]["domain"] == OrchestratorId.PERSONAL_DEVELOPMENT.value

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    async def test_no_orchestrator_returns_fallback(self, mock_logger):
        m = Meridian()
        # No orchestrators registered

        response = await m.process_message(
            user_input="something random",
            session_id="s2",
            user_id="u2",
        )

        assert "Could you tell me more" in response["response"]

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    @patch("ai.meridian.core.orchestrator.logger")
    @patch("ai.meridian.core.base_agent.logger")
    async def test_synthesizes_successful_results(self, mock_ba, mock_orch, mock_merid):
        """When DAG produces completed results with summaries, they are joined."""
        from ai.meridian.core.base_agent import BaseAgent
        from ai.meridian.core.types import AgentCapability

        class _SummaryAgent(BaseAgent):
            def __init__(self):
                super().__init__(AgentId.ECHO)

            async def process_task(self, task: AgentTask) -> AgentResult:
                return AgentResult(
                    task_id=task.task_id,
                    agent_id=self._agent_id,
                    status=TaskStatus.COMPLETED,
                    output={"summary": "Your resilience is strong."},
                    confidence=0.88,
                )

            def get_capabilities(self) -> AgentCapability:
                return AgentCapability(
                    agent_id=self._agent_id,
                    name="Stub",
                    tagline="t",
                    domain=OrchestratorId.PERSONAL_DEVELOPMENT,
                    actions=["a"],
                    description="d",
                )

        m = Meridian()
        orch = _FakeOrchestrator(OrchestratorId.PERSONAL_DEVELOPMENT)
        agent = _SummaryAgent()
        orch.register_agent(agent)

        node = DAGNode(
            node_id="n1",
            task=AgentTask(agent_id=AgentId.ECHO, action="assess"),
        )
        orch.set_plan([node])
        m.register_orchestrator(orch)

        response = await m.process_message(
            user_input="help with resilience and growth",
            session_id="s3",
            user_id="u3",
        )
        assert "resilience is strong" in response["response"]


class TestSessionContext:

    @patch("ai.meridian.core.meridian.logger")
    def test_get_session_context_none_initially(self, mock_logger):
        m = Meridian()
        assert m.get_session_context("nonexistent") is None

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    async def test_session_populated_after_message(self, mock_logger):
        m = Meridian()
        await m.process_message("hello", session_id="s1", user_id="u1")

        ctx = m.get_session_context("s1")
        assert ctx is not None
        assert ctx["user_id"] == "u1"
        assert len(ctx["history"]) >= 1

    @pytest.mark.asyncio
    @patch("ai.meridian.core.meridian.logger")
    async def test_clear_session(self, mock_logger):
        m = Meridian()
        await m.process_message("hi", session_id="s1", user_id="u1")
        m.clear_session("s1")
        assert m.get_session_context("s1") is None

    def test_clear_session_noop_for_unknown(self):
        m = Meridian()
        m.clear_session("does_not_exist")  # should not raise
