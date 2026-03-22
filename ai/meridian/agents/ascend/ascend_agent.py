from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.ascend.ascend_tools import (
    LeadershipSignature,
    TeamCompatibility,
    CoachingScenario,
    analyze_leadership_signature,
    assess_team_compatibility,
    generate_coaching_scenario,
)
from prism_inspire.core.log_config import logger


class AscendAgent(BaseAgent):
    """
    Ascend — The Leadership Catalyst.

    Develops leaders at every level through behavioral-informed coaching,
    leadership signature analysis, and team compatibility assessment.

    Supported actions:
    - leadership_signature: Analyze leadership style from behavioral profile
    - team_compatibility: Assess leader-team behavioral fit
    - coaching_scenario: Generate tailored coaching exercises
    - executive_coaching: Conduct a coaching conversation
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.ASCEND)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.ASCEND,
            name="Ascend",
            tagline="The Leadership Catalyst",
            domain=OrchestratorId.STRATEGIC_ADVISORY,
            actions=[
                "leadership_signature",
                "team_compatibility",
                "coaching_scenario",
                "executive_coaching",
            ],
            description=(
                "Develops leaders through behavioral-informed coaching, "
                "leadership signature analysis, team compatibility assessment, "
                "and Socratic executive coaching. Meets leaders where they are "
                "and calls them to rise."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "leadership_signature": self._leadership_signature,
            "team_compatibility": self._team_compatibility,
            "coaching_scenario": self._coaching_scenario,
            "executive_coaching": self._executive_coaching,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ASCEND,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Ascend",
            )

        return await handler(task)

    async def _leadership_signature(self, task: AgentTask) -> AgentResult:
        """Analyze leadership style from PRISM behavioral profile."""
        user_id = task.parameters.get("user_id") or task.context.get("user_id", "")
        behavioral_context = task.behavioral_context

        signature = analyze_leadership_signature(behavioral_context, user_id)

        if not behavioral_context:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ASCEND,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "To map your leadership signature, I need your PRISM "
                        "behavioral profile. Once you complete an assessment, "
                        "I can show you how your natural preferences translate "
                        "into leadership strengths."
                    ),
                    "has_profile": False,
                },
                confidence=0.90,
                reasoning="No behavioral context available for leadership analysis",
            )

        # Build narrative
        narrative_parts = [
            f"Your leadership signature is **{signature.primary_style}** "
            f"with **{signature.secondary_style}** as your secondary mode.",
            "",
            signature.style_description,
            "",
            "**Your Leadership Strengths:**",
        ]
        for strength in signature.strengths:
            narrative_parts.append(f"- {strength}")

        narrative_parts.append("")
        narrative_parts.append("**Watch For (Blind Spots):**")
        for blind_spot in signature.blind_spots:
            narrative_parts.append(f"- {blind_spot}")

        narrative_parts.append("")
        narrative_parts.append(
            f"**Executive Presence Score:** {signature.executive_presence_score:.0%} — "
            "this reflects the balance and range in your behavioral profile."
        )

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ASCEND,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "leadership_signature": signature.model_dump(),
                "has_profile": True,
            },
            confidence=0.85,
            reasoning=f"Leadership signature: {signature.primary_style} / {signature.secondary_style}",
        )

    async def _team_compatibility(self, task: AgentTask) -> AgentResult:
        """Assess leader-team behavioral compatibility."""
        leader_id = task.parameters.get("leader_id") or task.context.get("user_id", "")
        leader_context = task.behavioral_context
        team_contexts = task.parameters.get("team_contexts", [])

        compatibility = assess_team_compatibility(
            leader_context, team_contexts, leader_id
        )

        if not leader_context:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ASCEND,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "To assess team compatibility, I need your behavioral "
                        "profile. Complete a PRISM assessment to get started."
                    ),
                    "has_profile": False,
                },
                confidence=0.90,
            )

        # Build narrative
        narrative_parts = [
            f"**Team Compatibility Score:** {compatibility.compatibility_score:.0%}",
            "",
        ]

        if compatibility.synergies:
            narrative_parts.append("**Synergies:**")
            for synergy in compatibility.synergies:
                narrative_parts.append(f"- {synergy}")
            narrative_parts.append("")

        if compatibility.friction_areas:
            narrative_parts.append("**Friction Areas (Growth Opportunities):**")
            for friction in compatibility.friction_areas:
                narrative_parts.append(f"- {friction}")
            narrative_parts.append("")

        narrative_parts.append("**Recommendations:**")
        for rec in compatibility.recommendations:
            narrative_parts.append(f"- {rec}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ASCEND,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "compatibility": compatibility.model_dump(),
            },
            confidence=0.80,
            reasoning=(
                f"Team compatibility assessed: {compatibility.compatibility_score:.0%} "
                f"({len(compatibility.synergies)} synergies, "
                f"{len(compatibility.friction_areas)} friction areas)"
            ),
        )

    async def _coaching_scenario(self, task: AgentTask) -> AgentResult:
        """Generate a tailored coaching exercise."""
        focus_area = task.parameters.get("focus_area", "difficult_conversations")
        behavioral_context = task.behavioral_context

        scenario = generate_coaching_scenario(focus_area, behavioral_context)

        # Build narrative
        narrative_parts = [
            f"**Coaching Scenario: {scenario.development_focus}**",
            "",
            f"*Situation:* {scenario.scenario}",
            "",
            f"*The Challenge:* {scenario.challenge}",
            "",
            "**Coaching Questions to Reflect On:**",
        ]
        for i, question in enumerate(scenario.coaching_questions, 1):
            narrative_parts.append(f"{i}. {question}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ASCEND,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "coaching_scenario": scenario.model_dump(),
            },
            confidence=0.85,
            reasoning=f"Coaching scenario generated for focus area: {focus_area}",
        )

    async def _executive_coaching(self, task: AgentTask) -> AgentResult:
        """Conduct an executive coaching conversation."""
        user_id = task.parameters.get("user_id") or task.context.get("user_id", "")
        message = task.parameters.get("message", "")
        behavioral_context = task.behavioral_context
        coaching_focus = task.parameters.get("coaching_focus", "")

        if not message:
            # Opening the coaching conversation
            if behavioral_context:
                primary = behavioral_context.get("primary_preference", "")
                style_data = {
                    "gold": "Methodical Leader",
                    "green": "Servant Leader",
                    "blue": "Strategic Leader",
                    "red": "Directive Leader",
                }.get(primary, "leader")

                opening = (
                    f"Welcome. As a {style_data}, you bring real strengths to "
                    f"the table. What leadership challenge is on your mind today? "
                    f"What would make this conversation valuable for you?"
                )
            else:
                opening = (
                    "Welcome. I'm here to help you think through whatever "
                    "leadership challenge is top of mind. What's the situation "
                    "you'd like to explore?"
                )

            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ASCEND,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": opening,
                    "response": opening,
                    "coaching_mode": True,
                },
                confidence=0.85,
                reasoning="Executive coaching session opened",
            )

        # Respond with Socratic coaching approach
        response = (
            f"That's an important challenge. Let me ask you this: "
            f"what have you already tried, and what made you choose that approach? "
            f"Understanding your instinct here will help us find what's next."
        )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ASCEND,
            status=TaskStatus.COMPLETED,
            output={
                "summary": response,
                "response": response,
                "coaching_mode": True,
                "coaching_focus": coaching_focus,
            },
            confidence=0.75,
            reasoning="Executive coaching response — Socratic method",
            metadata={"requires_llm_enhancement": True},
        )
