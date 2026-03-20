from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.aura.aura_prompts import (
    AURA_SYSTEM_PROMPT,
    AURA_DEEP_DIVE_PROMPT,
    AURA_GROWTH_TRACKING_PROMPT,
)
from ai.meridian.agents.aura.aura_tools import (
    PRISMDimensions,
    BehavioralPreferenceMap,
    PRISMProfileRetriever,
    analyze_dimensions,
)
from prism_inspire.core.log_config import logger


class AuraAgent(BaseAgent):
    """
    Aura — The Insight Interpreter.

    The behavioral intelligence backbone of the Meridian system.
    ALL other agents consult Aura's output for behavioral context.

    Supported actions:
    - interpret_profile: Parse and explain a Behavioral Preference Map
    - deep_dive: Granular dimensional analysis
    - track_growth: Compare assessments over time
    - generate_context: Produce behavioral context for other agents
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
        prism_retriever: Optional[PRISMProfileRetriever] = None,
    ) -> None:
        super().__init__(AgentId.AURA)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._prism_retriever = prism_retriever or PRISMProfileRetriever()

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.AURA,
            name="Aura",
            tagline="The Insight Interpreter",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=[
                "interpret_profile",
                "deep_dive",
                "track_growth",
                "generate_context",
            ],
            description=(
                "Interprets PRISM Behavioral Preference Maps and provides "
                "behavioral intelligence that powers all other agents. "
                "Aura is the behavioral backbone of the Meridian system."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "interpret_profile": self._interpret_profile,
            "deep_dive": self._deep_dive,
            "track_growth": self._track_growth,
            "generate_context": self._generate_context,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Aura",
            )

        return await handler(task)

    async def _interpret_profile(self, task: AgentTask) -> AgentResult:
        """
        Parse and explain a Behavioral Preference Map in accessible,
        personalized language.
        """
        user_id = task.parameters.get("user_id") or task.context.get("user_id")
        prism_data = task.parameters.get("prism_data")

        if not user_id:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.FAILED,
                output={"error": "user_id is required"},
                confidence=0.0,
            )

        # Build or retrieve the Behavioral Preference Map
        bpm = await self._build_preference_map(user_id, prism_data)
        if bpm is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "I don't have a PRISM assessment on file for you yet. "
                        "Once you complete one, I can provide rich behavioral "
                        "insights to guide your development journey."
                    ),
                    "has_profile": False,
                },
                confidence=0.90,
                reasoning="No PRISM assessment found for user",
            )

        # Generate narrative interpretation
        narrative = self._generate_narrative(bpm)

        # Cache in memory service
        if self._memory_service:
            await self._memory_service.cache_behavioral_profile(
                user_id, bpm.to_context_dict()
            )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.AURA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "behavioral_preference_map": bpm.model_dump(),
                "has_profile": True,
            },
            confidence=0.88,
            reasoning="Profile interpreted from PRISM assessment data",
            metadata={"profile_version": bpm.version},
        )

    async def _deep_dive(self, task: AgentTask) -> AgentResult:
        """Granular dimensional analysis — explores interactions and nuances."""
        user_id = task.parameters.get("user_id") or task.context.get("user_id")
        dimension = task.parameters.get("dimension")  # optional focus dimension

        bpm = await self._get_or_build_map(user_id)
        if bpm is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": "A PRISM assessment is needed before we can do a deep dive.",
                    "has_profile": False,
                },
                confidence=0.90,
            )

        # Build deep-dive analysis
        analysis = self._build_deep_dive(bpm, dimension)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.AURA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": analysis["narrative"],
                "response": analysis["narrative"],
                "analysis": analysis,
                "behavioral_preference_map": bpm.model_dump(),
            },
            confidence=0.85,
            reasoning=f"Deep dive analysis on {'all dimensions' if not dimension else dimension}",
        )

    async def _track_growth(self, task: AgentTask) -> AgentResult:
        """Compare PRISM assessments over time to show behavioral growth."""
        user_id = task.parameters.get("user_id") or task.context.get("user_id")

        history = await self._prism_retriever.get_assessment_history(user_id)
        if len(history) < 2:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "Growth tracking needs at least two PRISM assessments "
                        "to compare. We'll be able to show your development "
                        "journey once you complete another assessment."
                    ),
                    "assessments_available": len(history),
                },
                confidence=0.90,
            )

        latest = history[0]
        previous = history[1]
        changes = self._compute_growth(previous, latest)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.AURA,
            status=TaskStatus.COMPLETED,
            output={
                "summary": changes["narrative"],
                "response": changes["narrative"],
                "growth_analysis": changes,
                "current_profile": latest.model_dump(),
                "previous_profile": previous.model_dump(),
            },
            confidence=0.82,
            reasoning="Growth tracked across assessment history",
        )

    async def _generate_context(self, task: AgentTask) -> AgentResult:
        """
        Generate behavioral context for other agents.
        This is the core function that makes Aura the intelligence backbone.
        """
        user_id = task.parameters.get("user_id") or task.context.get("user_id")
        requesting_agent = task.parameters.get("requesting_agent", "unknown")

        bpm = await self._get_or_build_map(user_id)
        if bpm is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.AURA,
                status=TaskStatus.COMPLETED,
                output={"behavioral_context": None, "has_profile": False},
                confidence=0.90,
                reasoning="No PRISM profile available for context generation",
            )

        context = bpm.to_context_dict()
        logger.info(
            f"Aura: generated behavioral context for {requesting_agent} "
            f"(user={user_id}, primary={bpm.primary_preference})"
        )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.AURA,
            status=TaskStatus.COMPLETED,
            output={
                "behavioral_context": context,
                "has_profile": True,
            },
            confidence=0.90,
            reasoning=f"Behavioral context generated for agent {requesting_agent}",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_build_map(
        self, user_id: Optional[str]
    ) -> Optional[BehavioralPreferenceMap]:
        """Try memory cache, then PRISM retriever."""
        if not user_id:
            return None

        # Check memory service cache first
        if self._memory_service:
            cached = await self._memory_service.get_behavioral_profile(user_id)
            if cached and "dimensions" in (cached.get("profile") or cached):
                profile_data = cached.get("profile", cached)
                return BehavioralPreferenceMap(
                    user_id=user_id,
                    dimensions=PRISMDimensions(**profile_data["dimensions"]),
                    primary_preference=profile_data.get("primary_preference", ""),
                    secondary_preference=profile_data.get("secondary_preference", ""),
                    behavioral_insights=profile_data.get("insights", []),
                    communication_preferences=profile_data.get("communication", {}),
                    growth_areas=profile_data.get("growth_areas", []),
                )

        return await self._build_preference_map(user_id, None)

    async def _build_preference_map(
        self, user_id: str, prism_data: Optional[dict[str, Any]]
    ) -> Optional[BehavioralPreferenceMap]:
        """Build a BehavioralPreferenceMap from raw PRISM data or retriever."""
        if prism_data and "dimensions" in prism_data:
            dims = PRISMDimensions(**prism_data["dimensions"])
        else:
            profile = await self._prism_retriever.get_profile(user_id)
            if profile:
                return profile
            return None

        analysis = analyze_dimensions(dims)
        return BehavioralPreferenceMap(
            user_id=user_id,
            dimensions=dims,
            primary_preference=analysis["primary"],
            secondary_preference=analysis["secondary"],
            behavioral_insights=analysis["insights"],
            communication_preferences=analysis["communication"],
            growth_areas=analysis["growth_areas"],
            stress_behaviors=analysis["stress_behaviors"],
            assessed_at=prism_data.get("assessed_at"),
        )

    def _generate_narrative(self, bpm: BehavioralPreferenceMap) -> str:
        """Generate a human-readable narrative from a Behavioral Preference Map."""
        dims = bpm.dimensions
        parts = []

        parts.append(
            f"Your PRISM profile reveals a rich behavioral landscape. "
            f"Your strongest preference is {_format_dim(bpm.primary_preference)} "
            f"(score: {_get_score(dims, bpm.primary_preference)}), complemented by "
            f"{_format_dim(bpm.secondary_preference)} "
            f"(score: {_get_score(dims, bpm.secondary_preference)})."
        )

        if bpm.behavioral_insights:
            parts.append(bpm.behavioral_insights[0])

        if bpm.growth_areas:
            parts.append(
                "For growth, " + bpm.growth_areas[0].lower()
                if bpm.growth_areas[0][0].isupper()
                else bpm.growth_areas[0]
            )

        return " ".join(parts)

    def _build_deep_dive(
        self, bpm: BehavioralPreferenceMap, focus_dimension: Optional[str]
    ) -> dict[str, Any]:
        """Build deep-dive analysis."""
        dims = bpm.dimensions
        all_scores = {
            "gold": dims.gold, "green": dims.green,
            "blue": dims.blue, "red": dims.red,
        }

        parts = []
        if focus_dimension and focus_dimension in all_scores:
            score = all_scores[focus_dimension]
            parts.append(
                f"Let's explore your {_format_dim(focus_dimension)} dimension "
                f"in depth. With a score of {score}, "
            )
            if score >= 70:
                parts.append(
                    "this is a strong natural preference for you. "
                    "It likely shows up consistently in how you approach work and relationships."
                )
            elif score >= 40:
                parts.append(
                    "this is a moderate preference — you can flex into this mode "
                    "when needed, but it may not be your default."
                )
            else:
                parts.append(
                    "this is less dominant in your profile. That doesn't mean you "
                    "can't operate here — it just takes more conscious effort."
                )
        else:
            parts.append(
                "Looking at how your four dimensions interact: "
                f"Gold ({dims.gold}), Green ({dims.green}), "
                f"Blue ({dims.blue}), Red ({dims.red}). "
            )

        if bpm.stress_behaviors:
            parts.append(
                "Under pressure, watch for: " + bpm.stress_behaviors[0].lower()
            )

        return {
            "narrative": " ".join(parts),
            "dimension_scores": all_scores,
            "focus": focus_dimension,
            "stress_behaviors": bpm.stress_behaviors,
            "communication_preferences": bpm.communication_preferences,
        }

    def _compute_growth(
        self,
        previous: BehavioralPreferenceMap,
        current: BehavioralPreferenceMap,
    ) -> dict[str, Any]:
        """Compute growth between two assessment snapshots."""
        changes = {}
        for dim in ["gold", "green", "blue", "red"]:
            prev_score = getattr(previous.dimensions, dim)
            curr_score = getattr(current.dimensions, dim)
            delta = curr_score - prev_score
            changes[dim] = {"previous": prev_score, "current": curr_score, "delta": delta}

        growing = [d for d, v in changes.items() if v["delta"] > 0]
        narrative_parts = ["Here's how your profile has evolved:"]
        if growing:
            for dim in growing:
                d = changes[dim]
                narrative_parts.append(
                    f"Your {_format_dim(dim)} preference has grown by "
                    f"{d['delta']} points ({d['previous']} → {d['current']}). "
                )
        else:
            narrative_parts.append(
                "Your profile has remained relatively stable, which can indicate "
                "a strong sense of self and consistent behavioral patterns."
            )

        return {"changes": changes, "narrative": " ".join(narrative_parts)}


def _format_dim(dim: str) -> str:
    labels = {"gold": "Gold", "green": "Green", "blue": "Blue", "red": "Red"}
    return labels.get(dim, dim.title())


def _get_score(dims: PRISMDimensions, dim: str) -> int:
    return getattr(dims, dim, 0)
