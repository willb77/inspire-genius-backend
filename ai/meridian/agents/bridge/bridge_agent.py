from __future__ import annotations

from typing import Any
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.bridge.bridge_prompts import (
    BRIDGE_SYSTEM_PROMPT,
    BRIDGE_PIPELINE_PROMPT,
    BRIDGE_MATCHING_PROMPT,
)
from ai.meridian.agents.bridge.bridge_tools import (
    PipelineHealth,
    StudentMatch,
    EmployerPipeline,
    assess_pipeline_health,
    match_student_to_employers,
    forecast_pipeline,
)
from prism_inspire.core.log_config import logger


PRISM_EMPLOYMENT_DISCLAIMER = (
    "PRISM behavioral preference data reflects self-reported behavioral "
    "tendencies and should not be used as the sole basis for any employment "
    "or placement decision. Student welfare is always the top priority."
)


class BridgeAgent(BaseAgent):
    """
    Bridge — The Talent Pipeline Architect.

    Connects schools, students, and employers with a tri-perspective
    approach, always prioritizing student welfare.

    Supported actions:
    - pipeline_health: Assess pipeline from school perspective
    - match_student: Match student to employers (student perspective)
    - employer_forecast: Pipeline forecast (employer perspective)
    - assess_placement: Track and evaluate placements
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.BRIDGE)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.BRIDGE,
            name="Bridge",
            tagline="The Talent Pipeline Architect",
            domain=OrchestratorId.ORGANIZATIONAL_INTELLIGENCE,
            actions=[
                "pipeline_health",
                "match_student",
                "employer_forecast",
                "assess_placement",
            ],
            description=(
                "Manages the school-student-employer talent pipeline with a "
                "tri-perspective approach. Provides pipeline health assessment, "
                "student-employer matching, and placement forecasting — always "
                "with student welfare as the top priority."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "pipeline_health": self._pipeline_health,
            "match_student": self._match_student,
            "employer_forecast": self._employer_forecast,
            "assess_placement": self._assess_placement,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Bridge",
            )

        return await handler(task)

    async def _pipeline_health(self, task: AgentTask) -> AgentResult:
        """Assess talent pipeline health from school perspective."""
        pipeline_data = task.parameters.get("pipeline_data", {})

        if not pipeline_data:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.FAILED,
                output={"error": "pipeline_data is required"},
                confidence=0.0,
            )

        health = assess_pipeline_health(pipeline_data)
        narrative = self._build_health_narrative(health)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.BRIDGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "pipeline_health": health.model_dump(),
            },
            confidence=0.85,
            reasoning=f"Pipeline health assessed: {health.status}",
        )

    async def _match_student(self, task: AgentTask) -> AgentResult:
        """Match a student to potential employers."""
        student_profile = task.parameters.get("student_profile", {})
        employers = task.parameters.get("employers", [])

        if not student_profile:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.FAILED,
                output={"error": "student_profile is required"},
                confidence=0.0,
            )

        if not employers:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": "No employers available for matching.",
                    "response": (
                        "There are currently no employers in the pipeline to "
                        "match with. We'll notify you when new opportunities arise."
                    ),
                    "matches": [],
                },
                confidence=0.90,
                reasoning="No employers provided for matching",
            )

        result = match_student_to_employers(student_profile, employers)
        narrative = self._build_match_narrative(result)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.BRIDGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "student_match": result.model_dump(),
                "disclaimer": PRISM_EMPLOYMENT_DISCLAIMER,
            },
            confidence=0.82,
            reasoning=f"Matched student to {len(result.employer_matches)} employers",
        )

    async def _employer_forecast(self, task: AgentTask) -> AgentResult:
        """Generate pipeline forecast from employer perspective."""
        pipeline_data = task.parameters.get("pipeline_data", {})

        if not pipeline_data:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.FAILED,
                output={"error": "pipeline_data is required"},
                confidence=0.0,
            )

        health = assess_pipeline_health(pipeline_data)
        fc = forecast_pipeline(health)

        summary = (
            f"Pipeline forecast: ~{fc['projected_placements_30d']:.0f} placements "
            f"in 30 days, ~{fc['projected_placements_90d']:.0f} in 90 days. "
            f"Risk level: {fc['risk_level']}."
        )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.BRIDGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": summary,
                "response": summary,
                "forecast": fc,
                "pipeline_health": health.model_dump(),
            },
            confidence=0.75,
            reasoning="Pipeline forecast generated from current metrics",
        )

    async def _assess_placement(self, task: AgentTask) -> AgentResult:
        """Track and evaluate a placement outcome."""
        placement = task.parameters.get("placement", {})

        if not placement:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.BRIDGE,
                status=TaskStatus.FAILED,
                output={"error": "placement data is required"},
                confidence=0.0,
            )

        student_id = placement.get("student_id", "unknown")
        employer_id = placement.get("employer_id", "unknown")
        status = placement.get("status", "active")
        satisfaction = placement.get("satisfaction_score", 0)

        if satisfaction >= 4:
            assessment = "strong"
            narrative = (
                f"Placement for student {student_id} at employer {employer_id} "
                f"is performing well (satisfaction: {satisfaction}/5)."
            )
        elif satisfaction >= 3:
            assessment = "adequate"
            narrative = (
                f"Placement for student {student_id} at employer {employer_id} "
                f"is adequate (satisfaction: {satisfaction}/5). Consider a "
                "check-in to identify improvement areas."
            )
        else:
            assessment = "at_risk"
            narrative = (
                f"Placement for student {student_id} at employer {employer_id} "
                f"needs attention (satisfaction: {satisfaction}/5). Recommend "
                "immediate student welfare check."
            )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.BRIDGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "placement_assessment": {
                    "student_id": student_id,
                    "employer_id": employer_id,
                    "status": status,
                    "satisfaction_score": satisfaction,
                    "assessment": assessment,
                },
            },
            confidence=0.80,
            reasoning=f"Placement assessed as {assessment}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_health_narrative(self, health: PipelineHealth) -> str:
        """Generate a human-readable pipeline health summary."""
        parts = [
            f"Pipeline {health.pipeline_id} (school: {health.school_id}): "
            f"{health.status.upper()}."
        ]
        parts.append(
            f"{health.active_students} active students, "
            f"{health.placement_rate:.0%} placement rate, "
            f"{health.avg_time_to_placement:.0f}-day average to placement."
        )
        if health.recommendations:
            parts.append(health.recommendations[0])
        return " ".join(parts)

    def _build_match_narrative(self, result: StudentMatch) -> str:
        """Generate a human-readable matching summary."""
        if not result.employer_matches:
            return f"No matches found for student {result.student_id}."

        top = result.employer_matches[0]
        parts = [
            f"Found {len(result.employer_matches)} match(es) for student "
            f"{result.student_id}."
        ]
        parts.append(
            f"Top match: {top.employer_name or top.employer_id} "
            f"(fit: {top.fit_score:.0%}) — {top.rationale}."
        )
        return " ".join(parts)
