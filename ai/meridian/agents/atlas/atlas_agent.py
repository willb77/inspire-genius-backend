from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.atlas.atlas_prompts import (
    ATLAS_SYSTEM_PROMPT,
    ATLAS_TEAM_ANALYSIS_PROMPT,
    ATLAS_WORKFORCE_PLAN_PROMPT,
)
from ai.meridian.agents.atlas.atlas_tools import (
    TeamComposition,
    TalentOptimizerScore,
    WorkforcePlan,
    analyze_team_composition,
    compute_talent_optimizer,
    build_workforce_plan,
)
from prism_inspire.core.log_config import logger


PRISM_EMPLOYMENT_DISCLAIMER = (
    "PRISM behavioral preferences are one data point among many and should "
    "not be the sole basis for employment decisions. All personnel decisions "
    "must comply with applicable employment laws and regulations."
)


class AtlasAgent(BaseAgent):
    """
    Atlas — The Organizational Architect.

    Designs teams, optimizes talent allocation, and plans workforce strategy
    using PRISM behavioral diversity metrics.

    Supported actions:
    - analyze_team: Team composition + behavioral diversity analysis
    - workforce_plan: Gap analysis + hiring recommendations
    - talent_optimizer: Score team behavioral diversity
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.ATLAS)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.ATLAS,
            name="Atlas",
            tagline="The Organizational Architect",
            domain=OrchestratorId.ORGANIZATIONAL_INTELLIGENCE,
            actions=[
                "analyze_team",
                "workforce_plan",
                "talent_optimizer",
            ],
            description=(
                "Designs team compositions using PRISM behavioral diversity, "
                "manages Job Blueprints, and provides workforce planning "
                "with gap analysis and hiring recommendations."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "analyze_team": self._analyze_team,
            "workforce_plan": self._workforce_plan,
            "talent_optimizer": self._talent_optimizer,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ATLAS,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Atlas",
            )

        return await handler(task)

    async def _analyze_team(self, task: AgentTask) -> AgentResult:
        """Analyze team composition and PRISM behavioral diversity."""
        team_id = task.parameters.get("team_id", "unknown")
        members = task.parameters.get("members", [])

        if not members:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ATLAS,
                status=TaskStatus.FAILED,
                output={"error": "members list is required"},
                confidence=0.0,
            )

        composition = analyze_team_composition(team_id, members)
        narrative = self._build_team_narrative(composition)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ATLAS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "composition": composition.model_dump(),
                "disclaimer": PRISM_EMPLOYMENT_DISCLAIMER,
            },
            confidence=0.85,
            reasoning="Team composition analyzed via PRISM diversity metrics",
        )

    async def _workforce_plan(self, task: AgentTask) -> AgentResult:
        """Generate workforce plan with gap analysis and hiring recommendations."""
        team_id = task.parameters.get("team_id", "unknown")
        members = task.parameters.get("members", [])
        target_roles = task.parameters.get("target_roles")

        if not members:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ATLAS,
                status=TaskStatus.FAILED,
                output={"error": "members list is required"},
                confidence=0.0,
            )

        composition = analyze_team_composition(team_id, members)
        plan = build_workforce_plan(composition, target_roles)
        narrative = self._build_plan_narrative(plan)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ATLAS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "workforce_plan": plan.model_dump(),
                "disclaimer": PRISM_EMPLOYMENT_DISCLAIMER,
            },
            confidence=0.82,
            reasoning="Workforce plan generated from behavioral gap analysis",
        )

    async def _talent_optimizer(self, task: AgentTask) -> AgentResult:
        """Score team behavioral diversity via Talent Optimizer."""
        team_id = task.parameters.get("team_id", "unknown")
        members = task.parameters.get("members", [])

        if not members:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ATLAS,
                status=TaskStatus.FAILED,
                output={"error": "members list is required"},
                confidence=0.0,
            )

        composition = analyze_team_composition(team_id, members)
        score = compute_talent_optimizer(composition)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ATLAS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Talent Optimizer Score: {score.diversity_score:.1f}/100 "
                    f"({score.balance_rating}). "
                    f"{len(score.complementarity_pairs)} complementary pairs identified."
                ),
                "response": (
                    f"Your team scores {score.diversity_score:.1f}/100 on behavioral "
                    f"diversity ({score.balance_rating}). "
                    f"Identified {len(score.complementarity_pairs)} complementary "
                    f"pairs that can strengthen collaboration."
                ),
                "talent_optimizer": score.model_dump(),
                "disclaimer": PRISM_EMPLOYMENT_DISCLAIMER,
            },
            confidence=0.87,
            reasoning="Talent optimizer score computed from PRISM diversity metrics",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_team_narrative(self, comp: TeamComposition) -> str:
        """Generate a human-readable team analysis narrative."""
        parts = []
        parts.append(
            f"Team analysis for {comp.team_id} ({len(comp.members)} members). "
            f"Behavioral diversity score: {comp.diversity_score:.1f}."
        )
        if comp.strengths:
            parts.append("Strengths: " + "; ".join(comp.strengths) + ".")
        if comp.gaps:
            parts.append("Gaps: " + "; ".join(comp.gaps) + ".")
        if comp.recommended_hires:
            parts.append(comp.recommended_hires[0])
        return " ".join(parts)

    def _build_plan_narrative(self, plan: WorkforcePlan) -> str:
        """Generate a human-readable workforce plan narrative."""
        parts = [f"Workforce plan for team {plan.team_id} ({plan.current_headcount} current)."]
        if plan.gaps:
            parts.append(f"Identified {len(plan.gaps)} behavioral gap(s).")
        if plan.hiring_recommendations:
            parts.append(
                f"{len(plan.hiring_recommendations)} hiring recommendation(s) generated."
            )
        if plan.internal_mobility:
            parts.append(
                f"{len(plan.internal_mobility)} internal mobility option(s) identified."
            )
        if not plan.gaps:
            parts.append("Team is well-balanced across all PRISM dimensions.")
        return " ".join(parts)
