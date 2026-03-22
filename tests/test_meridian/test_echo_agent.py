from __future__ import annotations
import pytest
from ai.meridian.agents.echo.echo_agent import EchoAgent
from ai.meridian.agents.echo.echo_tools import build_learning_path, create_micro_lesson
from ai.meridian.core.types import AgentId, AgentTask, OrchestratorId, TaskStatus


class TestEchoCapabilities:
    def test_id(self):
        assert EchoAgent().agent_id == AgentId.ECHO

    def test_capabilities(self):
        cap = EchoAgent().get_capabilities()
        assert cap.domain == OrchestratorId.PERSONAL_DEVELOPMENT
        assert "create_learning_path" in cap.actions

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        r = await EchoAgent().process_task(AgentTask(agent_id=AgentId.ECHO, action="nope", parameters={}))
        assert r.status == TaskStatus.FAILED


class TestLearningPath:
    @pytest.mark.asyncio
    async def test_create_path(self):
        r = await EchoAgent().process_task(AgentTask(
            agent_id=AgentId.ECHO, action="create_learning_path",
            parameters={"skill_gap": "public speaking", "user_id": "u1"},
            behavioral_context={"primary_preference": "green"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert "learning_path" in r.output
        assert len(r.output["learning_path"]["modules"]) > 0

    @pytest.mark.asyncio
    async def test_micro_lesson(self):
        r = await EchoAgent().process_task(AgentTask(
            agent_id=AgentId.ECHO, action="micro_lesson",
            parameters={"topic": "active listening"},
            behavioral_context={"primary_preference": "blue"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert "micro_lesson" in r.output

    @pytest.mark.asyncio
    async def test_track_progress_empty(self):
        r = await EchoAgent().process_task(AgentTask(
            agent_id=AgentId.ECHO, action="track_progress",
            parameters={"user_id": "u1"},
        ))
        assert r.output.get("progress") is None

    @pytest.mark.asyncio
    async def test_track_progress_after_path(self):
        agent = EchoAgent()
        await agent.process_task(AgentTask(
            agent_id=AgentId.ECHO, action="create_learning_path",
            parameters={"skill_gap": "sql", "user_id": "u1"},
        ))
        r = await agent.process_task(AgentTask(
            agent_id=AgentId.ECHO, action="track_progress",
            parameters={"user_id": "u1"},
        ))
        assert r.output["progress"] is not None


class TestEchoTools:
    def test_build_path_with_context(self):
        p = build_learning_path("leadership", {"primary_preference": "red"})
        assert p.behavioral_adaptation != ""

    def test_build_path_without_context(self):
        p = build_learning_path("coding")
        assert len(p.modules) > 0

    def test_micro_lesson(self):
        m = create_micro_lesson("delegation", {"primary_preference": "gold"})
        assert m.practice_exercise is not None
        assert "checklist" in m.practice_exercise.lower()
