from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.james.james_tools import (
    JobBlueprint,
    CandidateFitReport,
    InterviewGuide,
    generate_fit_report,
    generate_interview_questions,
)
from prism_inspire.core.log_config import logger


PRISM_DISCLAIMER = (
    "PRISM behavioral assessment data provides insights into behavioral "
    "preferences and tendencies. This data should not be used as the sole "
    "basis for employment, promotion, termination, or other personnel "
    "decisions. All decisions must consider the full context of an "
    "individual's qualifications, experience, and performance."
)


class JamesAgent(BaseAgent):
    """
    James — The Career Fit Specialist.

    Precision matching between behavioral profiles and Job Blueprints.

    Supported actions:
    - create_blueprint: Create a Job Blueprint with behavioral requirements
    - score_candidate: Score a candidate's PRISM results against a blueprint
    - generate_interview_guide: Create behavioral interview questions
    - compare_candidates: Generate candidate comparison matrix
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
        collaboration_service: Any = None,
    ) -> None:
        super().__init__(AgentId.JAMES)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._collaboration_service = collaboration_service
        # In-memory blueprint store
        self._blueprints: dict[str, JobBlueprint] = {}

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.JAMES,
            name="James",
            tagline="The Career Fit Specialist",
            domain=OrchestratorId.STRATEGIC_ADVISORY,
            actions=[
                "create_blueprint",
                "score_candidate",
                "generate_interview_guide",
                "compare_candidates",
            ],
            description=(
                "Precision matching between behavioral profiles and Job Blueprint "
                "requirements. Scores candidates, generates interview guides, and "
                "produces hiring manager insight packages."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        handlers = {
            "create_blueprint": self._create_blueprint,
            "score_candidate": self._score_candidate,
            "generate_interview_guide": self._generate_interview_guide,
            "compare_candidates": self._compare_candidates,
        }
        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.JAMES,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
            )
        return await handler(task)

    async def _create_blueprint(self, task: AgentTask) -> AgentResult:
        """Create a Job Blueprint with behavioral requirements."""
        params = task.parameters
        blueprint = JobBlueprint(
            title=params.get("title", "Untitled Role"),
            department=params.get("department", ""),
            description=params.get("description", ""),
            required_dimensions=params.get("required_dimensions", {}),
            dimension_weights=params.get("dimension_weights", {
                "gold": 0.25, "green": 0.25, "blue": 0.25, "red": 0.25,
            }),
            required_skills=params.get("required_skills", []),
            preferred_skills=params.get("preferred_skills", []),
            competencies=params.get("competencies", []),
        )

        self._blueprints[blueprint.blueprint_id] = blueprint

        # Store in memory for cross-agent access
        if self._memory_service:
            from ai.meridian.memory.memory_service import MemoryEntry, MemoryTier
            entry = MemoryEntry(
                tier=MemoryTier.LONG_TERM,
                agent_id="james",
                content=(
                    f"Job Blueprint: {blueprint.title} ({blueprint.department}). "
                    f"Required dimensions: {blueprint.required_dimensions}. "
                    f"Required skills: {', '.join(blueprint.required_skills)}."
                ),
                metadata={
                    "type": "job_blueprint",
                    "blueprint_id": blueprint.blueprint_id,
                    "blueprint_data": blueprint.model_dump(),
                },
            )
            await self._memory_service.store(entry)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.JAMES,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Job Blueprint created for {blueprint.title}.",
                "response": (
                    f"I've created the Job Blueprint for **{blueprint.title}**. "
                    f"The behavioral requirements are set and I'm ready to "
                    f"score candidates against this role."
                ),
                "blueprint": blueprint.model_dump(),
                "blueprint_id": blueprint.blueprint_id,
            },
            confidence=0.90,
            reasoning="Job Blueprint created with behavioral requirements",
        )

    async def _score_candidate(self, task: AgentTask) -> AgentResult:
        """Score a candidate's PRISM results against a Job Blueprint."""
        params = task.parameters
        candidate_id = params.get("candidate_id", "unknown")
        blueprint_id = params.get("blueprint_id", "")
        candidate_dimensions = params.get("candidate_dimensions", {})
        candidate_skills = params.get("candidate_skills", [])

        # Look up blueprint
        blueprint = self._blueprints.get(blueprint_id)
        if blueprint is None and params.get("blueprint_data"):
            blueprint = JobBlueprint(**params["blueprint_data"])

        if blueprint is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.JAMES,
                status=TaskStatus.FAILED,
                output={"error": f"Job Blueprint {blueprint_id} not found"},
                confidence=0.0,
            )

        if not candidate_dimensions:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.JAMES,
                status=TaskStatus.FAILED,
                output={"error": "candidate_dimensions is required (PRISM scores)"},
                confidence=0.0,
            )

        report = generate_fit_report(
            candidate_id=candidate_id,
            candidate_dimensions=candidate_dimensions,
            candidate_skills=candidate_skills,
            blueprint=blueprint,
        )

        # Store report in memory
        if self._memory_service:
            from ai.meridian.memory.memory_service import MemoryEntry, MemoryTier
            entry = MemoryEntry(
                tier=MemoryTier.SHORT_TERM,
                agent_id="james",
                content=(
                    f"Fit report for candidate {candidate_id} against blueprint "
                    f"{blueprint_id}: {report.tier} ({report.overall_fit_score:.0%})"
                ),
                metadata={
                    "type": "fit_report",
                    "candidate_id": candidate_id,
                    "blueprint_id": blueprint_id,
                    "session_id": task.context.get("session_id", "default"),
                    "report_data": report.model_dump(),
                },
            )
            await self._memory_service.store(entry)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.JAMES,
            status=TaskStatus.COMPLETED,
            output={
                "summary": report.narrative,
                "response": (
                    f"{report.narrative}\n\n"
                    f"Note: {PRISM_DISCLAIMER}"
                ),
                "fit_report": report.model_dump(),
                "tier": report.tier,
                "fit_score": report.overall_fit_score,
            },
            confidence=0.85,
            reasoning=f"Candidate scored: {report.tier} ({report.overall_fit_score:.0%})",
            metadata={"prism_disclaimer_included": True},
        )

    async def _generate_interview_guide(self, task: AgentTask) -> AgentResult:
        """Generate behavioral interview questions for a candidate."""
        params = task.parameters
        fit_report_data = params.get("fit_report")

        if not fit_report_data:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.JAMES,
                status=TaskStatus.FAILED,
                output={"error": "fit_report is required to generate interview guide"},
                confidence=0.0,
            )

        report = CandidateFitReport(**fit_report_data)
        blueprint = self._blueprints.get(report.blueprint_id)
        if blueprint is None and params.get("blueprint_data"):
            blueprint = JobBlueprint(**params["blueprint_data"])
        if blueprint is None:
            blueprint = JobBlueprint(title="Unknown Role")

        guide = generate_interview_questions(report, blueprint)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.JAMES,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Interview guide generated with {len(guide.questions)} questions "
                    f"focusing on {', '.join(guide.focus_dimensions) or 'general behavioral fit'}."
                ),
                "response": (
                    f"I've prepared a behavioral interview guide with "
                    f"{len(guide.questions)} targeted questions. "
                    f"{'Focus areas: ' + ', '.join(guide.focus_dimensions) + '. ' if guide.focus_dimensions else ''}"
                    f"{'Watch for: ' + '; '.join(guide.red_flags_to_probe) if guide.red_flags_to_probe else ''}"
                ),
                "interview_guide": guide.model_dump(),
            },
            confidence=0.85,
            reasoning="Interview guide generated from fit analysis",
        )

    async def _compare_candidates(self, task: AgentTask) -> AgentResult:
        """Generate a candidate comparison matrix."""
        params = task.parameters
        fit_reports_data = params.get("fit_reports", [])

        if len(fit_reports_data) < 2:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.JAMES,
                status=TaskStatus.FAILED,
                output={"error": "At least 2 fit reports required for comparison"},
                confidence=0.0,
            )

        reports = [CandidateFitReport(**r) for r in fit_reports_data]
        reports.sort(key=lambda r: r.overall_fit_score, reverse=True)

        comparison = {
            "candidates": [
                {
                    "candidate_id": r.candidate_id,
                    "tier": r.tier,
                    "overall_score": r.overall_fit_score,
                    "behavioral_fit": r.behavioral_fit,
                    "skill_fit": r.skill_fit,
                    "growth_potential": r.growth_potential,
                    "strengths": r.strengths,
                    "development_areas": r.development_areas,
                }
                for r in reports
            ],
            "recommendation": (
                f"Based on the analysis, candidate {reports[0].candidate_id} "
                f"shows the strongest overall fit ({reports[0].overall_fit_score:.0%}). "
                f"However, this is one input — please consider the full picture."
            ),
        }

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.JAMES,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Comparison of {len(reports)} candidates complete. "
                    f"Top candidate: {reports[0].candidate_id} ({reports[0].overall_fit_score:.0%})."
                ),
                "response": (
                    f"Here's the candidate comparison for this role. "
                    f"I've ranked {len(reports)} candidates by overall fit. "
                    f"Remember: these scores augment your judgment, they don't replace it.\n\n"
                    f"Note: {PRISM_DISCLAIMER}"
                ),
                "comparison": comparison,
            },
            confidence=0.83,
            reasoning=f"Compared {len(reports)} candidates",
            metadata={"prism_disclaimer_included": True},
        )

    def get_blueprint(self, blueprint_id: str) -> Optional[JobBlueprint]:
        """Retrieve a stored Job Blueprint."""
        return self._blueprints.get(blueprint_id)
