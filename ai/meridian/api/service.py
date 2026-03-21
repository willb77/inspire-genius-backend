from __future__ import annotations

from typing import Any, Optional
from prism_inspire.core.log_config import logger
from ai.meridian.core.meridian import Meridian
from ai.meridian.core.orchestrator import BaseOrchestrator
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, DAGNode,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.aura.aura_agent import AuraAgent
from ai.meridian.agents.nova.nova_agent import NovaAgent
from ai.meridian.agents.james.james_agent import JamesAgent
from ai.meridian.agents.echo.echo_agent import EchoAgent
from ai.meridian.agents.anchor.anchor_agent import AnchorAgent
from ai.meridian.agents.forge.forge_agent import ForgeAgent
from ai.meridian.analytics.dashboard import AgentAnalytics
from ai.meridian.agents.triage.triage_orchestrator import HiringTriageOrchestrator
from ai.meridian.collaboration.collaboration_service import CollaborationService
from ai.meridian.memory.memory_service import MemoryService


class PersonalDevelopmentOrchestrator(BaseOrchestrator):
    """
    Concrete orchestrator for the Personal Development domain.
    Manages Aura, Echo, Anchor, Forge.
    """

    def __init__(self) -> None:
        super().__init__(OrchestratorId.PERSONAL_DEVELOPMENT)

    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        """
        Build a DAG for personal development tasks.
        Routes to Aura, Echo, Anchor, or Forge based on intent.
        """
        user_id = context.get("user_id")
        behavioral_context = context.get("behavioral_context")
        text = intent.lower()

        # Anchor — stress, burnout, energy, resilience (check first for safety)
        anchor_keywords = [
            "stress", "burnout", "exhausted", "overwhelmed", "tired",
            "energy", "resilience", "recovery", "anxious", "struggling",
            "can't cope", "breaking point", "drained",
        ]
        if any(kw in text for kw in anchor_keywords):
            action = "stress_checkin"
            if any(kw in text for kw in ["protocol", "plan", "help me recover"]):
                action = "recovery_protocol"
            elif any(kw in text for kw in ["tips", "advice", "strategies"]):
                action = "resilience_tips"
            task = AgentTask(
                agent_id=AgentId.ANCHOR, action=action,
                parameters={"user_id": user_id, "query": intent},
                context=context, behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Forge — conflict, communication, stakeholders, meetings
        forge_keywords = [
            "conflict", "disagreement", "difficult conversation", "negotiat",
            "stakeholder", "influence", "communication", "meeting prep",
            "relationship", "tension", "confrontation", "persuad",
        ]
        if any(kw in text for kw in forge_keywords):
            action = "resolve_conflict"
            if any(kw in text for kw in ["playbook", "script", "prepare", "how to say"]):
                action = "communication_playbook"
            elif any(kw in text for kw in ["meeting", "briefing", "attendee"]):
                action = "meeting_briefing"
            task = AgentTask(
                agent_id=AgentId.FORGE, action=action,
                parameters={"user_id": user_id, "situation": intent},
                context=context, behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Echo — learning, skills, development, training
        echo_keywords = [
            "learn", "skill", "training", "course", "study",
            "develop", "competency", "tutorial", "lesson", "teach",
            "practice", "improve my",
        ]
        if any(kw in text for kw in echo_keywords):
            action = "create_learning_path"
            if any(kw in text for kw in ["quick", "micro", "lesson", "today"]):
                action = "micro_lesson"
            elif any(kw in text for kw in ["progress", "track", "status"]):
                action = "track_progress"
            skill = intent  # Use full intent as skill context
            task = AgentTask(
                agent_id=AgentId.ECHO, action=action,
                parameters={"user_id": user_id, "skill_gap": skill, "topic": skill},
                context=context, behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Aura — PRISM, behavioral, personality
        behavioral_keywords = [
            "prism", "personality", "behavior", "behavioral", "preference",
            "profile", "insight", "dimension", "gold", "green", "blue", "red",
            "self-discovery", "self discovery", "who am i", "my style",
            "my strengths", "my weaknesses",
        ]
        if any(kw in text for kw in behavioral_keywords):
            action = "interpret_profile"
            if any(kw in text for kw in ["deep", "detail", "granular", "explore"]):
                action = "deep_dive"
            elif any(kw in text for kw in ["growth", "change", "progress", "evolved"]):
                action = "track_growth"
            task = AgentTask(
                agent_id=AgentId.AURA, action=action,
                parameters={"user_id": user_id, "query": intent},
                context=context, behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Default: Aura generates behavioral context
        task = AgentTask(
            agent_id=AgentId.AURA, action="generate_context",
            parameters={"user_id": user_id, "requesting_agent": "meridian"},
            context=context, behavioral_context=behavioral_context,
        )
        return [DAGNode(task=task)]


class MeridianService:
    """
    Service layer that wires together Meridian, orchestrators, agents,
    and memory for the API routes.
    """

    def __init__(self, memory_service: Optional[MemoryService] = None) -> None:
        self._memory = memory_service or MemoryService()
        self._analytics = AgentAnalytics()
        self._meridian = Meridian()

        # Initialize Aura
        self._aura = AuraAgent(
            memory_service=self._memory,
        )

        # Initialize Personal Development Orchestrator with Aura
        pd_orchestrator = PersonalDevelopmentOrchestrator()
        pd_orchestrator.register_agent(self._aura)

        # Initialize remaining Personal Development agents
        self._echo = EchoAgent(memory_service=self._memory)
        self._anchor = AnchorAgent(memory_service=self._memory)
        self._forge = ForgeAgent(memory_service=self._memory)
        pd_orchestrator.register_agent(self._echo)
        pd_orchestrator.register_agent(self._anchor)
        pd_orchestrator.register_agent(self._forge)

        self._meridian.register_orchestrator(pd_orchestrator)

        # Initialize Collaboration Service
        self._collaboration = CollaborationService()

        # Initialize Nova and James
        self._nova = NovaAgent(
            memory_service=self._memory,
            collaboration_service=self._collaboration,
        )
        self._james = JamesAgent(
            memory_service=self._memory,
            collaboration_service=self._collaboration,
        )

        # Initialize Strategic Advisory Orchestrator (Nova-James triage)
        sa_orchestrator = HiringTriageOrchestrator()
        sa_orchestrator.register_agent(self._nova)
        sa_orchestrator.register_agent(self._james)
        self._meridian.register_orchestrator(sa_orchestrator)

        # Store orchestrators for agent listing
        self._orchestrators = {
            OrchestratorId.PERSONAL_DEVELOPMENT: pd_orchestrator,
            OrchestratorId.STRATEGIC_ADVISORY: sa_orchestrator,
        }

        logger.info("MeridianService initialized with Aura, Echo, Anchor, Forge, Nova, James agents")

    async def chat(
        self,
        user_id: str,
        session_id: str,
        message: str,
    ) -> dict[str, Any]:
        """
        Process a user message through Meridian.
        """
        # Load behavioral context from memory
        behavioral_context = await self._memory.get_behavioral_profile(user_id)

        result = await self._meridian.process_message(
            user_input=message,
            session_id=session_id,
            user_id=user_id,
            behavioral_context=behavioral_context,
        )

        # Record analytics for each agent result
        for agent_result in result.get("results", []):
            self._analytics.record_usage(
                agent_id=agent_result.get("agent_id", "unknown"),
                action=agent_result.get("metadata", {}).get("action", "unknown"),
                user_id=user_id,
                session_id=session_id,
                confidence=agent_result.get("confidence", 0.0),
                status=agent_result.get("status", "completed"),
            )

        return result

    def get_history(
        self, session_id: str, user_id: str
    ) -> Optional[list[dict[str, str]]]:
        """Get conversation history for a session."""
        ctx = self._meridian.get_session_context(session_id)
        if ctx is None:
            return None
        if ctx.get("user_id") != user_id:
            return None
        return ctx.get("history", [])

    async def submit_feedback(
        self,
        user_id: str,
        session_id: str,
        message_content: str,
        correction: str,
        rating: Optional[int] = None,
    ) -> str:
        """Store RLHF feedback as high-priority memory."""
        context = {"session_id": session_id}
        if rating is not None:
            context["rating"] = rating

        entry_id = await self._memory.store_feedback(
            agent_id="meridian",
            user_id=user_id,
            correction=correction,
            original_output=message_content,
            context=context,
        )
        logger.info(f"MeridianService: feedback stored {entry_id} for user {user_id}")
        return entry_id

    def get_analytics_summary(self) -> dict:
        """Get analytics dashboard summary for super-admin."""
        return self._analytics.get_dashboard_summary()

    def list_agent_capabilities(self) -> list[dict[str, Any]]:
        """List all registered agent capabilities."""
        agents = []

        # Collect from all orchestrators
        for orchestrator in self._orchestrators.values():
            for agent_id, agent in orchestrator._agents.items():
                cap = agent.get_capabilities()
                status = agent.report_status()
                agents.append({
                    "agent_id": cap.agent_id.value,
                    "name": cap.name,
                    "tagline": cap.tagline,
                    "domain": cap.domain.value,
                    "actions": cap.actions,
                    "description": cap.description,
                    "is_active": status.get("is_active", True),
                })

        return agents
