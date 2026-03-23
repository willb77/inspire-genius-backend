from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai.meridian.agents.triage.triage_orchestrator import HiringTriageOrchestrator
from ai.meridian.agents.nova.nova_agent import NovaAgent
from ai.meridian.agents.james.james_agent import JamesAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, DAGNode, OrchestratorId, TaskStatus,
)


def _make_orchestrator():
    orch = HiringTriageOrchestrator()
    nova = NovaAgent()
    james = JamesAgent()
    orch.register_agent(nova)
    orch.register_agent(james)
    return orch


class TestTriageOrchestratorRouting:
    @pytest.mark.asyncio
    async def test_triage_keyword_builds_full_dag(self):
        orch = _make_orchestrator()
        dag = await orch.plan(
            "Run the hiring triage for this candidate",
            {"user_id": "u1", "parameters": {"name": "Alice", "job_blueprint_id": "bp1"}},
        )
        assert len(dag) == 4
        agent_ids = [n.task.agent_id for n in dag]
        assert agent_ids[0] == AgentId.NOVA
        assert agent_ids[1] == AgentId.JAMES
        assert agent_ids[2] == AgentId.JAMES
        assert agent_ids[3] == AgentId.NOVA

    @pytest.mark.asyncio
    async def test_triage_dag_dependencies(self):
        orch = _make_orchestrator()
        dag = await orch.plan("Run triage evaluation", {"user_id": "u1", "parameters": {}})
        # Node 0: no deps
        assert dag[0].dependencies == []
        # Node 1 depends on node 0
        assert dag[1].dependencies == [dag[0].node_id]
        # Node 2 depends on node 1
        assert dag[2].dependencies == [dag[1].node_id]
        # Node 3 depends on nodes 1 and 2
        assert set(dag[3].dependencies) == {dag[1].node_id, dag[2].node_id}

    @pytest.mark.asyncio
    async def test_candidate_submission_routes_to_nova(self):
        orch = _make_orchestrator()
        dag = await orch.plan("submit candidate for review", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.NOVA
        assert dag[0].task.action == "submit_candidate"

    @pytest.mark.asyncio
    async def test_blueprint_routes_to_james(self):
        orch = _make_orchestrator()
        dag = await orch.plan("create a job blueprint for PM role", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.JAMES
        assert dag[0].task.action == "create_blueprint"

    @pytest.mark.asyncio
    async def test_score_routes_to_james(self):
        orch = _make_orchestrator()
        dag = await orch.plan("run fit score analysis for this candidate", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.JAMES
        assert dag[0].task.action == "score_candidate"

    @pytest.mark.asyncio
    async def test_interview_routes_to_james(self):
        orch = _make_orchestrator()
        dag = await orch.plan("generate interview guide", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.JAMES
        assert dag[0].task.action == "generate_interview_guide"

    @pytest.mark.asyncio
    async def test_career_routes_to_nova(self):
        orch = _make_orchestrator()
        dag = await orch.plan("help me with my career path", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.NOVA
        assert dag[0].task.action == "career_strategy"

    @pytest.mark.asyncio
    async def test_default_routes_to_nova_career(self):
        orch = _make_orchestrator()
        dag = await orch.plan("hello", {"user_id": "u1", "parameters": {}})
        assert len(dag) == 1
        assert dag[0].task.agent_id == AgentId.NOVA


class TestTriageOrchestratorExecution:
    @pytest.mark.asyncio
    async def test_single_node_execution(self):
        """Test that a single-node DAG executes and returns results."""
        orch = _make_orchestrator()
        dag = await orch.plan(
            "What career path should I take?",
            {"user_id": "u1", "behavioral_context": {"primary_preference": "red", "secondary_preference": "blue"}, "parameters": {}},
        )
        results = await orch.execute_dag(dag)
        assert len(results) == 1
        assert results[0].status == TaskStatus.COMPLETED
        assert results[0].agent_id == AgentId.NOVA


class TestCrossAgentMemory:
    @pytest.mark.asyncio
    async def test_nova_submission_stored_in_memory(self):
        """Nova stores candidate data in memory, accessible by James."""
        memory = MagicMock()
        memory.store = AsyncMock(return_value="entry-1")
        memory.get_behavioral_profile = AsyncMock(return_value=None)

        nova = NovaAgent(memory_service=memory)
        james = JamesAgent(memory_service=memory)

        # Nova submits candidate
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="submit_candidate",
            parameters={
                "name": "Alice",
                "job_blueprint_id": "bp-1",
                "skills": ["python"],
            },
            context={"session_id": "s1"},
        )
        result = await nova.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        memory.store.assert_awaited_once()

        # Verify the stored entry has candidate data
        stored_entry = memory.store.call_args[0][0]
        assert stored_entry.metadata["type"] == "candidate_submission"
        assert stored_entry.metadata["candidate_data"]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_james_blueprint_stored_in_memory(self):
        """James stores blueprint data in memory, accessible by Nova."""
        memory = MagicMock()
        memory.store = AsyncMock(return_value="entry-1")

        james = JamesAgent(memory_service=memory)
        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="create_blueprint",
            parameters={
                "title": "Data Scientist",
                "required_dimensions": {"gold": 50, "green": 40, "blue": 85, "red": 55},
                "required_skills": ["python", "ml"],
            },
        )
        result = await james.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        memory.store.assert_awaited_once()

        stored_entry = memory.store.call_args[0][0]
        assert stored_entry.metadata["type"] == "job_blueprint"
