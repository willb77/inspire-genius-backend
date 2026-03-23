from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai.meridian.agents.james.james_agent import JamesAgent
from ai.meridian.agents.james.james_tools import (
    JobBlueprint,
    CandidateFitReport,
    InterviewGuide,
    score_behavioral_fit,
    score_skill_fit,
    assess_growth_potential,
    classify_candidate,
    generate_fit_report,
    generate_interview_questions,
)
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentCapability, OrchestratorId, TaskStatus,
)


def _make_agent(memory=None):
    return JamesAgent(memory_service=memory)


SAMPLE_BLUEPRINT = {
    "title": "Senior Engineer",
    "department": "Engineering",
    "required_dimensions": {"gold": 60, "green": 50, "blue": 80, "red": 65},
    "dimension_weights": {"gold": 0.20, "green": 0.15, "blue": 0.40, "red": 0.25},
    "required_skills": ["python", "sql", "aws"],
    "preferred_skills": ["docker", "kubernetes"],
}


class TestJamesCapabilities:
    def test_agent_id(self):
        assert _make_agent().agent_id == AgentId.JAMES

    def test_capabilities(self):
        cap = _make_agent().get_capabilities()
        assert cap.domain == OrchestratorId.STRATEGIC_ADVISORY
        assert "score_candidate" in cap.actions
        assert "create_blueprint" in cap.actions
        assert "generate_interview_guide" in cap.actions
        assert "compare_candidates" in cap.actions

    @pytest.mark.asyncio
    async def test_unknown_action_fails(self):
        result = await _make_agent().process_task(
            AgentTask(agent_id=AgentId.JAMES, action="nope", parameters={})
        )
        assert result.status == TaskStatus.FAILED


class TestCreateBlueprint:
    @pytest.mark.asyncio
    async def test_create_stores_blueprint(self):
        memory = MagicMock()
        memory.store = AsyncMock(return_value="e1")
        agent = _make_agent(memory=memory)

        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="create_blueprint",
            parameters=SAMPLE_BLUEPRINT,
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        bp_id = result.output["blueprint_id"]
        assert agent.get_blueprint(bp_id) is not None
        assert agent.get_blueprint(bp_id).title == "Senior Engineer"
        memory.store.assert_awaited_once()


class TestScoreCandidate:
    @pytest.mark.asyncio
    async def test_score_strong_fit(self):
        memory = MagicMock()
        memory.store = AsyncMock(return_value="e1")
        agent = _make_agent(memory=memory)

        # Create blueprint first
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        agent._blueprints[bp.blueprint_id] = bp

        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="score_candidate",
            parameters={
                "candidate_id": "c1",
                "blueprint_id": bp.blueprint_id,
                "candidate_dimensions": {"gold": 58, "green": 52, "blue": 78, "red": 63},
                "candidate_skills": ["python", "sql", "aws", "docker"],
            },
        )
        result = await agent.process_task(task)

        assert result.status == TaskStatus.COMPLETED
        assert "fit_report" in result.output
        assert result.output["fit_score"] > 0.6
        assert result.metadata.get("prism_disclaimer_included") is True

    @pytest.mark.asyncio
    async def test_score_misalignment(self):
        agent = _make_agent()
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        agent._blueprints[bp.blueprint_id] = bp

        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="score_candidate",
            parameters={
                "candidate_id": "c2",
                "blueprint_id": bp.blueprint_id,
                "candidate_dimensions": {"gold": 90, "green": 20, "blue": 30, "red": 25},
                "candidate_skills": ["excel"],
            },
        )
        result = await agent.process_task(task)
        assert result.output["tier"] == "misalignment_detected"

    @pytest.mark.asyncio
    async def test_score_missing_blueprint(self):
        result = await _make_agent().process_task(
            AgentTask(
                agent_id=AgentId.JAMES,
                action="score_candidate",
                parameters={
                    "candidate_id": "c1",
                    "blueprint_id": "nonexistent",
                    "candidate_dimensions": {"gold": 50, "green": 50, "blue": 50, "red": 50},
                },
            )
        )
        assert result.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_score_missing_dimensions(self):
        agent = _make_agent()
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        agent._blueprints[bp.blueprint_id] = bp
        result = await agent.process_task(
            AgentTask(
                agent_id=AgentId.JAMES,
                action="score_candidate",
                parameters={"candidate_id": "c1", "blueprint_id": bp.blueprint_id},
            )
        )
        assert result.status == TaskStatus.FAILED


class TestGenerateInterviewGuide:
    @pytest.mark.asyncio
    async def test_generate_guide(self):
        agent = _make_agent()
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        agent._blueprints[bp.blueprint_id] = bp

        report = generate_fit_report(
            "c1",
            {"gold": 40, "green": 45, "blue": 60, "red": 50},
            ["python"],
            bp,
        )

        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="generate_interview_guide",
            parameters={
                "fit_report": report.model_dump(),
                "blueprint_data": bp.model_dump(),
            },
        )
        result = await agent.process_task(task)
        assert result.status == TaskStatus.COMPLETED
        guide = result.output["interview_guide"]
        assert len(guide["questions"]) >= 1

    @pytest.mark.asyncio
    async def test_generate_guide_missing_report(self):
        result = await _make_agent().process_task(
            AgentTask(
                agent_id=AgentId.JAMES,
                action="generate_interview_guide",
                parameters={},
            )
        )
        assert result.status == TaskStatus.FAILED


class TestCompareCandidates:
    @pytest.mark.asyncio
    async def test_compare_two_candidates(self):
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        r1 = generate_fit_report("c1", {"gold": 58, "green": 52, "blue": 78, "red": 63}, ["python", "sql", "aws"], bp)
        r2 = generate_fit_report("c2", {"gold": 40, "green": 45, "blue": 60, "red": 50}, ["python"], bp)

        task = AgentTask(
            agent_id=AgentId.JAMES,
            action="compare_candidates",
            parameters={"fit_reports": [r1.model_dump(), r2.model_dump()]},
        )
        result = await _make_agent().process_task(task)
        assert result.status == TaskStatus.COMPLETED
        assert len(result.output["comparison"]["candidates"]) == 2

    @pytest.mark.asyncio
    async def test_compare_needs_two(self):
        result = await _make_agent().process_task(
            AgentTask(
                agent_id=AgentId.JAMES,
                action="compare_candidates",
                parameters={"fit_reports": [{"candidate_id": "c1"}]},
            )
        )
        assert result.status == TaskStatus.FAILED


class TestJamesTools:
    def test_score_behavioral_fit_perfect(self):
        bp = JobBlueprint(title="Role", required_dimensions={"gold": 70, "green": 70, "blue": 70, "red": 70})
        score, dims = score_behavioral_fit({"gold": 70, "green": 70, "blue": 70, "red": 70}, bp)
        assert score == pytest.approx(1.0, abs=0.01)
        assert all(d.assessment == "strong" for d in dims)

    def test_score_behavioral_fit_mismatch(self):
        bp = JobBlueprint(title="Role", required_dimensions={"gold": 80, "green": 80, "blue": 80, "red": 80})
        score, dims = score_behavioral_fit({"gold": 30, "green": 30, "blue": 30, "red": 30}, bp)
        assert score < 0.5
        assert all(d.assessment == "development_needed" for d in dims)

    def test_score_skill_fit_full_match(self):
        bp = JobBlueprint(title="R", required_skills=["python", "sql"], preferred_skills=["docker"])
        score = score_skill_fit(["python", "sql", "docker"], bp)
        assert score > 0.9

    def test_score_skill_fit_no_match(self):
        bp = JobBlueprint(title="R", required_skills=["python", "sql"])
        score = score_skill_fit(["java"], bp)
        assert score < 0.1

    def test_classify_strong_fit(self):
        assert classify_candidate(0.80, 0.75) == "strong_fit"

    def test_classify_potential_fit(self):
        assert classify_candidate(0.60, 0.55) == "potential_fit"

    def test_classify_misalignment(self):
        assert classify_candidate(0.30, 0.25) == "misalignment_detected"

    def test_generate_fit_report(self):
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        report = generate_fit_report("c1", {"gold": 58, "green": 52, "blue": 78, "red": 63}, ["python", "sql", "aws"], bp)
        assert isinstance(report, CandidateFitReport)
        assert report.overall_fit_score > 0
        assert report.tier in ("strong_fit", "potential_fit", "misalignment_detected")

    def test_generate_interview_questions(self):
        bp = JobBlueprint(**SAMPLE_BLUEPRINT)
        report = generate_fit_report("c1", {"gold": 40, "green": 40, "blue": 40, "red": 40}, [], bp)
        guide = generate_interview_questions(report, bp)
        assert isinstance(guide, InterviewGuide)
        assert len(guide.questions) >= 1
