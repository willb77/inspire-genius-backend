from __future__ import annotations

from typing import Any
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.nexus.nexus_prompts import (
    NEXUS_SYSTEM_PROMPT,
    NEXUS_CALIBRATION_PROMPT,
)
from ai.meridian.agents.nexus.nexus_tools import (
    CulturalProfile,
    CulturalAdaptation,
    SUPPORTED_LANGUAGES,
    get_cultural_profile,
    adapt_communication,
)
from prism_inspire.core.log_config import logger


class NexusAgent(BaseAgent):
    """
    Nexus — The Cultural Navigator.

    Cross-cultural communication intelligence using Hofstede's 6-dimension
    framework with 16-language support.

    Supported actions:
    - cultural_profile: Get Hofstede cultural profile for a country
    - adapt_communication: Cross-cultural communication recommendations
    - calibrate_style: Adjust Meridian's coaching style for cultural context
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.NEXUS)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.NEXUS,
            name="Nexus",
            tagline="The Cultural Navigator",
            domain=OrchestratorId.ORGANIZATIONAL_INTELLIGENCE,
            actions=[
                "cultural_profile",
                "adapt_communication",
                "calibrate_style",
            ],
            description=(
                "Provides cross-cultural communication intelligence using "
                "Hofstede's 6-dimension framework. Supports cultural profiling, "
                "adaptation recommendations, and coaching style calibration "
                f"across {len(SUPPORTED_LANGUAGES)} languages."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "cultural_profile": self._cultural_profile,
            "adapt_communication": self._adapt_communication,
            "calibrate_style": self._calibrate_style,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NEXUS,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Nexus",
            )

        return await handler(task)

    async def _cultural_profile(self, task: AgentTask) -> AgentResult:
        """Get Hofstede cultural profile for a country."""
        country = task.parameters.get("country", "")

        if not country:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NEXUS,
                status=TaskStatus.FAILED,
                output={"error": "country is required"},
                confidence=0.0,
            )

        profile = get_cultural_profile(country)
        narrative = self._build_profile_narrative(profile)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NEXUS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "cultural_profile": profile.model_dump(),
            },
            confidence=0.85,
            reasoning=f"Cultural profile retrieved for {country}",
        )

    async def _adapt_communication(self, task: AgentTask) -> AgentResult:
        """Generate cross-cultural communication recommendations."""
        source = task.parameters.get("source_country", "")
        target = task.parameters.get("target_country", "")

        if not source or not target:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NEXUS,
                status=TaskStatus.FAILED,
                output={"error": "source_country and target_country are required"},
                confidence=0.0,
            )

        adaptation = adapt_communication(source, target)
        narrative = self._build_adaptation_narrative(adaptation)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NEXUS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "adaptation": adaptation.model_dump(),
            },
            confidence=0.83,
            reasoning=f"Cross-cultural adaptation generated: {source} -> {target}",
        )

    async def _calibrate_style(self, task: AgentTask) -> AgentResult:
        """Adjust Meridian's coaching style for a cultural context."""
        country = task.parameters.get("country", "")
        language = task.parameters.get("language", "en")

        if not country:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.NEXUS,
                status=TaskStatus.FAILED,
                output={"error": "country is required for style calibration"},
                confidence=0.0,
            )

        profile = get_cultural_profile(country)
        calibration = self._build_calibration(profile, language)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.NEXUS,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Coaching style calibrated for {country} ({language}).",
                "response": calibration["narrative"],
                "calibration": calibration,
                "cultural_profile": profile.model_dump(),
            },
            confidence=0.80,
            reasoning=f"Style calibrated for {country} cultural context",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_profile_narrative(self, profile: CulturalProfile) -> str:
        """Generate a human-readable cultural profile summary."""
        scores = profile.hofstede_scores
        parts = [
            f"Cultural profile for {profile.country} "
            f"({profile.communication_style.replace('_', '-')} communication style)."
        ]

        highlights = []
        for dim, score in scores.items():
            label = dim.replace("_", " ").title()
            if score >= 75:
                highlights.append(f"high {label} ({score})")
            elif score <= 25:
                highlights.append(f"low {label} ({score})")

        if highlights:
            parts.append("Notable dimensions: " + ", ".join(highlights) + ".")

        parts.append(
            "Remember: these are research-based national tendencies, "
            "not descriptions of individuals."
        )
        return " ".join(parts)

    def _build_adaptation_narrative(self, adaptation: CulturalAdaptation) -> str:
        """Generate a human-readable adaptation summary."""
        parts = [
            f"Adapting communication from {adaptation.source_culture} "
            f"to {adaptation.target_culture}."
        ]
        if adaptation.adaptations:
            parts.append(adaptation.adaptations[0])
        if adaptation.style_recommendations:
            parts.append(adaptation.style_recommendations[0])
        return " ".join(parts)

    def _build_calibration(
        self, profile: CulturalProfile, language: str
    ) -> dict[str, Any]:
        """Build coaching style calibration from cultural profile."""
        scores = profile.hofstede_scores

        feedback_style = (
            "indirect and face-saving"
            if scores.get("power_distance", 50) > 60
            else "direct and transparent"
        )
        achievement_focus = (
            "collective success"
            if scores.get("individualism", 50) < 45
            else "individual growth"
        )
        structure_level = (
            "high structure with clear expectations"
            if scores.get("uncertainty_avoidance", 50) > 65
            else "flexible with room for exploration"
        )
        formality = (
            "formal and respectful of hierarchy"
            if scores.get("power_distance", 50) > 60
            else "casual and egalitarian"
        )

        narrative = (
            f"For coaching in a {profile.country} context: use {feedback_style} "
            f"feedback, emphasize {achievement_focus}, provide {structure_level} "
            f"guidance, and maintain a {formality} tone."
        )

        return {
            "narrative": narrative,
            "feedback_style": feedback_style,
            "achievement_focus": achievement_focus,
            "structure_level": structure_level,
            "formality": formality,
            "language": language,
            "language_supported": language in SUPPORTED_LANGUAGES,
        }
