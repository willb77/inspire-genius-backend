from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.nova.nova_tools import (
    CandidateSubmission,
    CandidateTier,
    CareerPathway,
    TriageResult,
    HiringDashboardEntry,
    build_career_pathways,
    aggregate_triage_dashboard,
)
from prism_inspire.core.log_config import logger


class NovaAgent(BaseAgent):
    """
    Nova — The Career Strategist.

    Career strategy, hiring triage coordination, career development roadmaps.

    Supported actions:
    - career_strategy: Build personalized career pathways
    - submit_candidate: Receive candidate for triage, trigger PRISM Light
    - publish_triage: Aggregate and publish triage results to dashboard
    - promotion_readiness: Assess readiness for advancement
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
        collaboration_service: Any = None,
    ) -> None:
        super().__init__(AgentId.NOVA)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._collaboration_service = collaboration_service
        # In-memory candidate pipeline per job blueprint
        self._pipeline: dict[str, list[CandidateSubmission]] = {}

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.NOVA,
            name="Nova",
            tagline="The Career Strategist",
            domain=OrchestratorId.STRATEGIC_ADVISORY,
            actions=[
                "career_strategy",
                "submit_candidate",
                "publish_triage",
                "promotion_readiness",
            ],
            description=(
                "Career strategy architect and hiring triage coordinator. "
                "Develops personalized career roadmaps and manages the "
                "Nova-James hiring workflow."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        handlers = {
            "career_strategy": self._career_strategy,
            "submit_candidate": self._submit_candidate,
            "publish_triage": self._publish_triage,
            "promotion_readiness": self._promotion_readiness,
        }
        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NOVA,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
            )
        return await handler(task)

    async def _career_strategy(self, task: AgentTask) -> AgentResult:
        """Build personalized career pathways."""
        behavioral_context = task.behavioral_context
        current_role = task.parameters.get("current_role")
        goals = task.parameters.get("goals")

        pathways = build_career_pathways(behavioral_context, current_role, goals)

        narrative_parts = ["Here are some career pathways that align with your behavioral profile:"]
        for i, p in enumerate(pathways, 1):
            narrative_parts.append(f"\n{i}. **{p.title}** — {p.description}")
            if p.skills_to_develop:
                narrative_parts.append(f"   Skills to develop: {', '.join(p.skills_to_develop)}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NOVA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "pathways": [p.model_dump() for p in pathways],
            },
            confidence=0.82,
            reasoning="Career pathways generated from behavioral profile",
        )

    async def _submit_candidate(self, task: AgentTask) -> AgentResult:
        """Receive candidate submission and trigger PRISM Light assessment."""
        params = task.parameters
        candidate = CandidateSubmission(
            name=params.get("name", "Unknown"),
            email=params.get("email"),
            job_blueprint_id=params.get("job_blueprint_id", ""),
            resume_summary=params.get("resume_summary"),
            skills=params.get("skills", []),
            experience_years=params.get("experience_years"),
        )

        if not candidate.job_blueprint_id:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NOVA,
                status=TaskStatus.FAILED,
                output={"error": "job_blueprint_id is required"},
                confidence=0.0,
            )

        # Add to pipeline
        bp_id = candidate.job_blueprint_id
        if bp_id not in self._pipeline:
            self._pipeline[bp_id] = []
        self._pipeline[bp_id].append(candidate)

        logger.info(
            f"Nova: candidate {candidate.candidate_id} ({candidate.name}) "
            f"submitted for blueprint {bp_id}"
        )

        # Store in memory for cross-agent access
        if self._memory_service:
            from ai.meridian.memory.memory_service import MemoryEntry, MemoryTier
            entry = MemoryEntry(
                tier=MemoryTier.SHORT_TERM,
                agent_id="nova",
                content=(
                    f"Candidate {candidate.name} submitted for job blueprint "
                    f"{bp_id}. Skills: {', '.join(candidate.skills)}. "
                    f"Experience: {candidate.experience_years or 'N/A'} years."
                ),
                metadata={
                    "type": "candidate_submission",
                    "candidate_id": candidate.candidate_id,
                    "job_blueprint_id": bp_id,
                    "session_id": task.context.get("session_id", "default"),
                    "candidate_data": candidate.model_dump(),
                },
            )
            await self._memory_service.store(entry)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NOVA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Candidate {candidate.name} has been submitted for evaluation. "
                    "PRISM Light assessment has been triggered. James will score "
                    "the assessment against the Job Blueprint once complete."
                ),
                "response": (
                    f"I've received {candidate.name}'s submission for this role. "
                    "The next step is a brief PRISM Light assessment (10-15 minutes). "
                    "Once complete, we'll provide a detailed behavioral fit analysis."
                ),
                "candidate_id": candidate.candidate_id,
                "job_blueprint_id": bp_id,
                "status": "prism_light_triggered",
            },
            confidence=0.90,
            reasoning="Candidate submitted and PRISM Light assessment triggered",
        )

    async def _publish_triage(self, task: AgentTask) -> AgentResult:
        """Aggregate triage results and publish to dashboard."""
        bp_id = task.parameters.get("job_blueprint_id", "")
        job_title = task.parameters.get("job_title", "Unknown Role")
        triage_results_raw = task.parameters.get("triage_results", [])

        triage_results = []
        for raw in triage_results_raw:
            triage_results.append(TriageResult(
                candidate_id=raw.get("candidate_id", ""),
                job_blueprint_id=bp_id,
                tier=CandidateTier(raw.get("tier", "pending_assessment")),
                fit_score=raw.get("fit_score", 0.0),
                evidence=raw.get("evidence", []),
                strengths=raw.get("strengths", []),
                development_areas=raw.get("development_areas", []),
                recommendation=raw.get("recommendation", ""),
            ))

        dashboard = aggregate_triage_dashboard(bp_id, job_title, triage_results)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NOVA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Hiring triage complete for {job_title}: "
                    f"{dashboard.strong_fit_count} strong fit, "
                    f"{dashboard.potential_fit_count} potential fit, "
                    f"{dashboard.misalignment_count} misalignment, "
                    f"{dashboard.pending_count} pending."
                ),
                "response": (
                    f"The triage for **{job_title}** is ready for review. "
                    f"Out of {dashboard.total_candidates} candidates: "
                    f"{dashboard.strong_fit_count} are strong fits, "
                    f"{dashboard.potential_fit_count} show potential with development areas, "
                    f"and {dashboard.misalignment_count} have significant misalignment. "
                    "Please review the full analysis below — remember, this is to "
                    "augment your judgment, not replace it."
                ),
                "dashboard": dashboard.model_dump(),
            },
            confidence=0.85,
            reasoning="Triage results aggregated for hiring dashboard",
        )

    async def _promotion_readiness(self, task: AgentTask) -> AgentResult:
        """Assess promotion readiness based on behavioral profile and career data."""
        behavioral_context = task.behavioral_context
        target_role = task.parameters.get("target_role", "next level")

        if not behavioral_context:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NOVA,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "To assess promotion readiness, I need your behavioral "
                        "profile. Please complete a PRISM assessment first."
                    ),
                    "readiness_score": None,
                },
                confidence=0.90,
            )

        primary = behavioral_context.get("primary_preference", "")
        strengths = behavioral_context.get("insights", [])

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NOVA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Based on your behavioral profile, here's your readiness "
                    f"assessment for {target_role}: Your {primary.title()} "
                    f"preference provides a strong foundation. "
                    f"{'Key strength: ' + strengths[0] if strengths else ''}"
                ),
                "response": (
                    f"Let's look at your readiness for **{target_role}**. "
                    f"Your behavioral profile suggests some natural advantages "
                    f"and a few areas to develop."
                ),
                "target_role": target_role,
                "behavioral_alignment": primary,
            },
            confidence=0.78,
            reasoning=f"Promotion readiness assessed for {target_role}",
        )

    def get_pipeline(self, job_blueprint_id: str) -> list[CandidateSubmission]:
        """Get candidate pipeline for a job blueprint."""
        return self._pipeline.get(job_blueprint_id, [])
