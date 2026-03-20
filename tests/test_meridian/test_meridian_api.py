from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai.meridian.api.service import MeridianService, PersonalDevelopmentOrchestrator
from ai.meridian.api.schemas import (
    MeridianChatRequest,
    MeridianFeedbackRequest,
)
from ai.meridian.core.types import (
    AgentId, AgentTask, DAGNode, OrchestratorId, TaskStatus,
)


# ---------------------------------------------------------------------------
# Tests: PersonalDevelopmentOrchestrator
# ---------------------------------------------------------------------------

class TestPersonalDevelopmentOrchestrator:
    @pytest.mark.asyncio
    async def test_plan_routes_behavioral_to_aura(self):
        orch = PersonalDevelopmentOrchestrator()
        dag = await orch.plan(
            "Tell me about my PRISM personality profile",
            {"user_id": "u1", "behavioral_context": None},
        )
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.AURA
        assert dag[0].task.action == "interpret_profile"

    @pytest.mark.asyncio
    async def test_plan_deep_dive_keywords(self):
        orch = PersonalDevelopmentOrchestrator()
        dag = await orch.plan(
            "I want to explore my behavioral profile in detail",
            {"user_id": "u1", "behavioral_context": None},
        )
        assert dag[0].task.action == "deep_dive"

    @pytest.mark.asyncio
    async def test_plan_growth_keywords(self):
        orch = PersonalDevelopmentOrchestrator()
        dag = await orch.plan(
            "How has my behavior changed and growth over time?",
            {"user_id": "u1", "behavioral_context": None},
        )
        assert dag[0].task.action == "track_growth"

    @pytest.mark.asyncio
    async def test_plan_default_generates_context(self):
        orch = PersonalDevelopmentOrchestrator()
        dag = await orch.plan(
            "I feel stressed about work",
            {"user_id": "u1", "behavioral_context": None},
        )
        assert dag[0].task.agent_id == AgentId.AURA
        assert dag[0].task.action == "generate_context"


# ---------------------------------------------------------------------------
# Tests: MeridianService
# ---------------------------------------------------------------------------

class TestMeridianService:
    def _make_service(self):
        memory = MagicMock()
        memory.get_behavioral_profile = AsyncMock(return_value=None)
        memory.cache_behavioral_profile = AsyncMock()
        memory.store_feedback = AsyncMock(return_value="fb-123")
        memory.store = AsyncMock(return_value="entry-1")
        return MeridianService(memory_service=memory), memory

    @pytest.mark.asyncio
    async def test_chat_returns_response(self):
        svc, _ = self._make_service()
        result = await svc.chat(
            user_id="u1",
            session_id="s1",
            message="Tell me about my PRISM profile",
        )
        assert "response" in result
        assert isinstance(result["response"], str)
        assert "intent" in result

    @pytest.mark.asyncio
    async def test_chat_routes_behavioral_to_aura(self):
        svc, _ = self._make_service()
        result = await svc.chat(
            user_id="u1",
            session_id="s1",
            message="What does my PRISM personality say about me?",
        )
        # Aura should have produced a result (no profile found, but completed)
        assert result["response"] is not None

    def test_get_history_none_for_unknown_session(self):
        svc, _ = self._make_service()
        assert svc.get_history("nonexistent", "u1") is None

    @pytest.mark.asyncio
    async def test_get_history_after_chat(self):
        svc, _ = self._make_service()
        await svc.chat(user_id="u1", session_id="s1", message="Hello")
        history = svc.get_history("s1", "u1")
        assert history is not None
        assert len(history) >= 2  # user + assistant
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"

    def test_get_history_wrong_user(self):
        """History should not be returned for a different user."""
        svc, _ = self._make_service()
        # Manually set up session context
        svc._meridian._session_context["s1"] = {
            "user_id": "u1",
            "history": [{"role": "user", "content": "hi"}],
        }
        assert svc.get_history("s1", "u2") is None

    @pytest.mark.asyncio
    async def test_submit_feedback(self):
        svc, memory = self._make_service()
        entry_id = await svc.submit_feedback(
            user_id="u1",
            session_id="s1",
            message_content="original response",
            correction="better response",
            rating=4,
        )
        assert entry_id == "fb-123"
        memory.store_feedback.assert_awaited_once_with(
            agent_id="meridian",
            user_id="u1",
            correction="better response",
            original_output="original response",
            context={"session_id": "s1", "rating": 4},
        )

    def test_list_agent_capabilities(self):
        svc, _ = self._make_service()
        agents = svc.list_agent_capabilities()
        assert len(agents) >= 1
        aura = next((a for a in agents if a["agent_id"] == "aura"), None)
        assert aura is not None
        assert aura["name"] == "Aura"
        assert aura["tagline"] == "The Insight Interpreter"
        assert "interpret_profile" in aura["actions"]
        assert aura["is_active"] is True


# ---------------------------------------------------------------------------
# Tests: Pydantic schemas
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_chat_request_validation(self):
        req = MeridianChatRequest(message="Hello Meridian")
        assert req.message == "Hello Meridian"
        assert req.session_id is None

    def test_chat_request_with_session(self):
        req = MeridianChatRequest(message="Hello", session_id="s1")
        assert req.session_id == "s1"

    def test_feedback_request_validation(self):
        req = MeridianFeedbackRequest(
            session_id="s1",
            message_content="original",
            correction="better",
            rating=5,
        )
        assert req.rating == 5
