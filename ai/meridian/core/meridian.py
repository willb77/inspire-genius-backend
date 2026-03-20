from __future__ import annotations

from typing import Optional
from ai.meridian.core.types import (
    AgentResult, OrchestratorId, UserIntent, AgentId,
)
from ai.meridian.core.orchestrator import BaseOrchestrator
from prism_inspire.core.log_config import logger


class Meridian:
    """
    The unified mentor layer - the single user-facing persona.

    Meridian handles:
    - Intent classification and domain routing
    - Multi-agent response synthesis into a single coherent voice
    - Conversation continuity and session management
    - Communication style adaptation (formality, depth, cultural context)
    """

    PERSONA_PROMPT = (
        "You are Meridian, a warm and insightful AI mentor. "
        "Your role is to guide users at the intersection of potential and purpose. "
        "Speak in a unified, coherent voice — never reveal the specialist agents behind you. "
        "Adapt your communication style to the user's preferences and cultural context."
    )

    # Maps orchestrator domains to their registered orchestrator instances
    _orchestrators: dict[OrchestratorId, BaseOrchestrator]

    def __init__(self) -> None:
        self._orchestrators = {}
        self._session_context: dict[str, dict] = {}

    def register_orchestrator(self, orchestrator: BaseOrchestrator) -> None:
        """Register a domain orchestrator."""
        self._orchestrators[orchestrator.orchestrator_id] = orchestrator
        logger.info(f"Meridian: registered orchestrator {orchestrator.orchestrator_id.value}")

    async def classify_intent(self, user_input: str, session_id: str) -> UserIntent:
        """
        Classify user intent and route to the appropriate domain.

        Uses LLM-based classification to determine:
        - Which domain orchestrator should handle this
        - What type of intent it is
        - What entities are referenced
        - Whether a process template matches
        """
        # Domain keyword heuristics as fallback / initial routing
        domain = self._route_to_domain(user_input)

        # Check for template matches across orchestrators
        matched_template = None
        orchestrator = self._orchestrators.get(domain)
        if orchestrator:
            template = orchestrator.match_template(user_input)
            if template:
                matched_template = template.template_id

        return UserIntent(
            raw_input=user_input,
            domain=domain,
            intent_type="general_query",
            confidence=0.75,
            entities={},
            matched_template=matched_template,
        )

    async def process_message(
        self,
        user_input: str,
        session_id: str,
        user_id: str,
        behavioral_context: Optional[dict] = None,
    ) -> dict:
        """
        Process a user message through the full Meridian pipeline:
        1. Classify intent
        2. Route to domain orchestrator
        3. Orchestrator builds and executes DAG
        4. Synthesize results into coherent response
        """
        # Store session context
        if session_id not in self._session_context:
            self._session_context[session_id] = {
                "user_id": user_id,
                "history": [],
            }
        self._session_context[session_id]["history"].append({
            "role": "user",
            "content": user_input,
        })

        # 1. Classify intent
        intent = await self.classify_intent(user_input, session_id)
        logger.info(
            f"Meridian: classified intent for session {session_id} → "
            f"domain={intent.domain.value}, confidence={intent.confidence:.2f}"
        )

        # 2. Route to orchestrator
        orchestrator = self._orchestrators.get(intent.domain)
        if not orchestrator:
            return {
                "response": "I'm here to help. Could you tell me more about what you're looking for?",
                "intent": intent.model_dump(),
                "results": [],
            }

        # 3. Build and execute DAG
        context = {
            "session_id": session_id,
            "user_id": user_id,
            "behavioral_context": behavioral_context,
            "session_history": self._session_context[session_id]["history"],
        }
        dag = await orchestrator.plan(intent.raw_input, context)
        results = await orchestrator.execute_dag(dag)

        # 4. Synthesize response
        response_text = self._synthesize_response(results, intent)

        self._session_context[session_id]["history"].append({
            "role": "assistant",
            "content": response_text,
        })

        return {
            "response": response_text,
            "intent": intent.model_dump(),
            "results": [r.model_dump() for r in results],
        }

    def _route_to_domain(self, user_input: str) -> OrchestratorId:
        """Route user input to the appropriate domain orchestrator."""
        text = user_input.lower()

        personal_keywords = [
            "prism", "personality", "behavior", "learning", "burnout",
            "stress", "energy", "conflict", "communication", "self",
            "growth", "resilience", "interpersonal", "emotion",
        ]
        org_keywords = [
            "team", "organization", "compliance", "audit", "workforce",
            "culture", "pipeline", "employer", "school", "policy",
            "gdpr", "eeoc", "ada", "soc", "blueprint",
        ]
        strategic_keywords = [
            "career", "hire", "hiring", "interview", "candidate",
            "research", "leadership", "executive", "coaching", "student",
            "university", "academic", "strategy", "promotion",
        ]

        scores = {
            OrchestratorId.PERSONAL_DEVELOPMENT: sum(
                1 for kw in personal_keywords if kw in text
            ),
            OrchestratorId.ORGANIZATIONAL_INTELLIGENCE: sum(
                1 for kw in org_keywords if kw in text
            ),
            OrchestratorId.STRATEGIC_ADVISORY: sum(
                1 for kw in strategic_keywords if kw in text
            ),
        }

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return OrchestratorId.PERSONAL_DEVELOPMENT  # default domain
        return best

    def _synthesize_response(
        self, results: list[AgentResult], intent: UserIntent
    ) -> str:
        """
        Synthesize multiple agent results into a single coherent response.
        In production, this calls the LLM with Meridian's persona prompt.
        """
        if not results:
            return "I'd love to help you with that. Could you share a bit more detail?"

        successful = [r for r in results if r.status.value == "completed"]
        if not successful:
            return (
                "I'm working on that for you, but I need a moment to gather "
                "the right insights. Could you provide some additional context?"
            )

        # Aggregate outputs from successful agents
        combined_outputs = []
        for result in successful:
            if result.output.get("summary"):
                combined_outputs.append(result.output["summary"])
            elif result.output.get("response"):
                combined_outputs.append(result.output["response"])

        if combined_outputs:
            return " ".join(combined_outputs)

        return "I've analyzed your request. Let me know if you'd like to dive deeper into any aspect."

    def get_session_context(self, session_id: str) -> Optional[dict]:
        """Retrieve session context for conversation continuity."""
        return self._session_context.get(session_id)

    def clear_session(self, session_id: str) -> None:
        """Clear session context."""
        self._session_context.pop(session_id, None)
