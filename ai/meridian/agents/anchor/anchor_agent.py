from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.anchor.anchor_prompts import ANCHOR_PRIVACY_NOTICE
from ai.meridian.agents.anchor.anchor_tools import (
    EnergyLevel,
    StressCheckIn,
    assess_burnout_risk,
    build_recovery_protocol,
)
from prism_inspire.core.log_config import logger


class AnchorAgent(BaseAgent):
    """
    Anchor — The Performance Resilience Coach.

    Burnout prevention, energy management, recovery protocols.
    ALL interactions are STRICTLY PRIVATE — never surfaced to management.

    Supported actions:
    - stress_checkin: Record and assess current stress/energy levels
    - recovery_protocol: Generate a personalized recovery plan
    - resilience_tips: Provide behavioral-adapted resilience strategies
    """

    def __init__(self, llm_provider: Any = None, memory_service: Any = None) -> None:
        super().__init__(AgentId.ANCHOR)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._checkin_history: dict[str, list[int]] = {}

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.ANCHOR,
            name="Anchor",
            tagline="The Performance Resilience Coach",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=["stress_checkin", "recovery_protocol", "resilience_tips"],
            description=(
                "Burnout prevention and energy management coach. "
                "All interactions are strictly private — never surfaced to management."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        handlers = {
            "stress_checkin": self._stress_checkin,
            "recovery_protocol": self._recovery_protocol,
            "resilience_tips": self._resilience_tips,
        }
        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id, agent_id=AgentId.ANCHOR,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"}, confidence=0.0,
            )
        return await handler(task)

    async def _stress_checkin(self, task: AgentTask) -> AgentResult:
        user_id = task.parameters.get("user_id") or task.context.get("user_id", "")
        stress_score = task.parameters.get("stress_score", 5)
        energy = task.parameters.get("energy_level", "moderate")

        try:
            energy_level = EnergyLevel(energy)
        except ValueError:
            energy_level = EnergyLevel.MODERATE

        # Track history
        if user_id not in self._checkin_history:
            self._checkin_history[user_id] = []
        self._checkin_history[user_id].append(stress_score)
        recent = self._checkin_history[user_id][-5:]

        assessment = assess_burnout_risk(stress_score, energy_level, recent)

        if assessment["needs_escalation"]:
            return AgentResult(
                task_id=task.task_id, agent_id=AgentId.ANCHOR,
                status=TaskStatus.AWAITING_HUMAN,
                output={
                    "summary": (
                        "I'm concerned about your stress level. Please consider "
                        "reaching out to a trusted person or professional support. "
                        "You don't have to handle this alone."
                    ),
                    "response": (
                        f"{ANCHOR_PRIVACY_NOTICE}\n\n"
                        "I can see you're going through a really tough time right now. "
                        "Your wellbeing matters more than any task or deadline. "
                        "I'd encourage you to reach out to someone you trust, "
                        "or contact your Employee Assistance Program for confidential support."
                    ),
                    "assessment": assessment,
                    "is_private": True,
                },
                confidence=0.95,
                reasoning="High stress detected — escalation recommended",
            )

        risk = assessment["risk_level"]
        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ANCHOR,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Stress level: {stress_score}/10, energy: {energy_level.value}. "
                    f"Burnout risk: {risk}. "
                    + (assessment["recommendations"][0] if assessment["recommendations"] else "")
                ),
                "response": (
                    f"{ANCHOR_PRIVACY_NOTICE}\n\n"
                    f"Thanks for checking in. Your stress is at {stress_score}/10 "
                    f"and your energy is {energy_level.value}. "
                    f"{'That is a lot to carry. ' if risk == 'high' else ''}"
                    f"Here are some things that might help:\n" +
                    "\n".join(f"- {r}" for r in assessment["recommendations"])
                ),
                "assessment": assessment,
                "is_private": True,
            },
            confidence=0.85,
            reasoning=f"Stress check-in: risk={risk}",
        )

    async def _recovery_protocol(self, task: AgentTask) -> AgentResult:
        risk_level = task.parameters.get("risk_level", "moderate")
        protocol = build_recovery_protocol(risk_level, task.behavioral_context)

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ANCHOR,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"{protocol.title}: {'; '.join(protocol.steps[:2])}",
                "response": (
                    f"{ANCHOR_PRIVACY_NOTICE}\n\n"
                    f"**{protocol.title}**\n\n" +
                    "\n".join(f"{i+1}. {s}" for i, s in enumerate(protocol.steps))
                ),
                "protocol": protocol.model_dump(),
                "is_private": True,
            },
            confidence=0.85,
        )

    async def _resilience_tips(self, task: AgentTask) -> AgentResult:
        behavioral_context = task.behavioral_context
        primary = behavioral_context.get("primary_preference", "") if behavioral_context else ""

        tips = {
            "gold": [
                "Build recovery time into your schedule — treat it like any other commitment",
                "When overwhelmed, make a priority list. Seeing structure calms your mind",
                "Perfectionism is your strength and your trap. Practice 'good enough'",
            ],
            "green": [
                "You absorb others' stress. Set emotional boundaries to protect your energy",
                "Schedule social recharge time with people who lift you up",
                "It's okay to say no to helping someone else when you need help yourself",
            ],
            "blue": [
                "Track your energy patterns — data helps you see burnout before you feel it",
                "Give yourself permission to not have all the answers right now",
                "Step away from analysis when stuck. Your best insights come after rest",
            ],
            "red": [
                "Rest is not the absence of productivity — it's what makes productivity possible",
                "Your drive is your superpower, but even superpowers need recharging",
                "Delegate. Letting others contribute isn't weakness, it's leadership",
            ],
        }

        selected = tips.get(primary, [
            "Take three deep breaths right now",
            "Identify one thing you can let go of today",
            "Move your body — even a short walk helps",
        ])

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ANCHOR,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Resilience tips: {selected[0]}",
                "response": (
                    f"{ANCHOR_PRIVACY_NOTICE}\n\n"
                    "Here are some resilience strategies tailored for you:\n" +
                    "\n".join(f"- {t}" for t in selected)
                ),
                "tips": selected,
                "is_private": True,
            },
            confidence=0.85,
        )
