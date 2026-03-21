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
        For now, routes behavioral questions to Aura.
        """
        user_id = context.get("user_id")
        behavioral_context = context.get("behavioral_context")

        # Check if this is a behavioral/PRISM-related query
        text = intent.lower()
        behavioral_keywords = [
            "prism", "personality", "behavior", "behavioral", "preference",
            "profile", "insight", "dimension", "gold", "green", "blue", "red",
            "self-discovery", "self discovery", "who am i", "my style",
            "my strengths", "my weaknesses", "growth",
        ]

        if any(kw in text for kw in behavioral_keywords):
            # Route to Aura
            action = "interpret_profile"
            if any(kw in text for kw in ["deep", "detail", "granular", "explore"]):
                action = "deep_dive"
            elif any(kw in text for kw in ["growth", "change", "progress", "evolved"]):
                action = "track_growth"

            task = AgentTask(
                agent_id=AgentId.AURA,
                action=action,
                parameters={"user_id": user_id, "query": intent},
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Default: ask Aura for context, then handle generically
        task = AgentTask(
            agent_id=AgentId.AURA,
            action="generate_context",
            parameters={"user_id": user_id, "requesting_agent": "meridian"},
            context=context,
            behavioral_context=behavioral_context,
        )
        return [DAGNode(task=task)]


class MeridianService:
    """
    Service layer that wires together Meridian, orchestrators, agents,
    and memory for the API routes.
    """

    def __init__(self, memory_service: Optional[MemoryService] = None) -> None:
        self._memory = memory_service or MemoryService()
        self._meridian = Meridian()

        # Initialize Aura
        self._aura = AuraAgent(
            memory_service=self._memory,
        )

        # Initialize Personal Development Orchestrator with Aura
        pd_orchestrator = PersonalDevelopmentOrchestrator()
        pd_orchestrator.register_agent(self._aura)
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

        logger.info("MeridianService initialized with Aura, Nova, James agents")

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
