from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.forge.forge_tools import (
    analyze_conflict,
    build_communication_playbook,
    build_meeting_briefing,
)
from prism_inspire.core.log_config import logger


class ForgeAgent(BaseAgent):
    """
    Forge — The Interpersonal Effectiveness Strategist.

    Conflict resolution, stakeholder influence, communication coaching.

    Supported actions:
    - resolve_conflict: Analyze conflict and provide resolution strategies
    - communication_playbook: Build a tailored communication plan
    - meeting_briefing: Generate pre-meeting briefing with stakeholder insights
    """

    def __init__(self, llm_provider: Any = None, memory_service: Any = None) -> None:
        super().__init__(AgentId.FORGE)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.FORGE,
            name="Forge",
            tagline="The Interpersonal Effectiveness Strategist",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=["resolve_conflict", "communication_playbook", "meeting_briefing"],
            description=(
                "Conflict resolution, stakeholder influence mapping, and "
                "communication coaching. Adapts strategies to PRISM profiles "
                "of all parties involved."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        handlers = {
            "resolve_conflict": self._resolve_conflict,
            "communication_playbook": self._communication_playbook,
            "meeting_briefing": self._meeting_briefing,
        }
        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id, agent_id=AgentId.FORGE,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"}, confidence=0.0,
            )
        return await handler(task)

    async def _resolve_conflict(self, task: AgentTask) -> AgentResult:
        situation = task.parameters.get("situation", "a workplace disagreement")
        counterpart_context = task.parameters.get("counterpart_context")
        analysis = analyze_conflict(task.behavioral_context, counterpart_context, situation)

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.FORGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"Conflict analysis: {analysis.dynamic}. "
                    f"Approach: {analysis.recommended_approach}"
                ),
                "response": (
                    f"Let's work through this together. Here's what I see:\n\n"
                    f"**The Dynamic**: {analysis.dynamic}\n\n"
                    f"**Friction points**: {'; '.join(analysis.friction_points)}\n\n"
                    f"**Common ground**: {'; '.join(analysis.common_ground)}\n\n"
                    f"**Recommended approach**: {analysis.recommended_approach}"
                ),
                "analysis": analysis.model_dump(),
            },
            confidence=0.80,
            reasoning=f"Conflict analysis for {analysis.dynamic}",
        )

    async def _communication_playbook(self, task: AgentTask) -> AgentResult:
        situation = task.parameters.get("situation", "an important conversation")
        counterpart_context = task.parameters.get("counterpart_context")
        playbook = build_communication_playbook(situation, task.behavioral_context, counterpart_context)

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.FORGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Communication playbook ready for: {situation}",
                "response": (
                    f"**{playbook.title}**\n\n"
                    f"Opening options:\n" +
                    "\n".join(f'- "{s}"' for s in playbook.opening_scripts) +
                    f"\n\nKey phrases to use:\n" +
                    "\n".join(f"- {p}" for p in playbook.key_phrases) +
                    f"\n\nAvoid:\n" +
                    "\n".join(f"- {p}" for p in playbook.phrases_to_avoid) +
                    f"\n\nAfterward, debrief with:\n" +
                    "\n".join(f"- {q}" for q in playbook.debrief_questions)
                ),
                "playbook": playbook.model_dump(),
            },
            confidence=0.82,
        )

    async def _meeting_briefing(self, task: AgentTask) -> AgentResult:
        meeting_purpose = task.parameters.get("meeting_purpose", "team meeting")
        attendees = task.parameters.get("attendees", [])
        briefing = build_meeting_briefing(meeting_purpose, attendees)

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.FORGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Meeting briefing ready: {meeting_purpose}",
                "response": (
                    f"**Pre-Meeting Briefing: {meeting_purpose}**\n\n"
                    f"Attendee insights:\n" +
                    "\n".join(f"- {a['tip']}" for a in briefing.attendee_insights) +
                    f"\n\nTalking points:\n" +
                    "\n".join(f"- {t}" for t in briefing.talking_points) +
                    f"\n\nRisks to watch: {', '.join(briefing.risks)}"
                ),
                "briefing": briefing.model_dump(),
            },
            confidence=0.82,
        )
