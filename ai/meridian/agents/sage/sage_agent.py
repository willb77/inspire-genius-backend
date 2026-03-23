from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.sage.sage_tools import (
    ResearchSynthesis,
    ExecutiveBriefing,
    synthesize_research,
    build_executive_briefing,
    search_knowledge_base,
)
from prism_inspire.core.log_config import logger


class SageAgent(BaseAgent):
    """
    Sage — The Knowledge Synthesizer.

    Distills research, frameworks, and organizational knowledge into
    clear, actionable intelligence grounded in evidence.

    Supported actions:
    - research_synthesis: Synthesize research on a topic with evidence quality rating
    - executive_briefing: Build a scannable, decision-ready briefing
    - knowledge_search: Search organizational knowledge base via vector similarity
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.SAGE)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.SAGE,
            name="Sage",
            tagline="The Knowledge Synthesizer",
            domain=OrchestratorId.STRATEGIC_ADVISORY,
            actions=[
                "research_synthesis",
                "executive_briefing",
                "knowledge_search",
            ],
            description=(
                "Distills complex research, frameworks, and organizational "
                "knowledge into clear, actionable intelligence. Evidence-based, "
                "rigorous, and always honest about what the data does and does "
                "not support."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "research_synthesis": self._research_synthesis,
            "executive_briefing": self._executive_briefing,
            "knowledge_search": self._knowledge_search,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SAGE,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Sage",
            )

        return await handler(task)

    async def _research_synthesis(self, task: AgentTask) -> AgentResult:
        """Synthesize research on a topic with evidence quality assessment."""
        topic = task.parameters.get("topic")
        domain = task.parameters.get("domain")

        if not topic:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SAGE,
                status=TaskStatus.FAILED,
                output={"error": "topic is required"},
                confidence=0.0,
            )

        synthesis = synthesize_research(topic, domain)

        # Build narrative
        narrative_parts = [
            f"Here is a research synthesis on **{topic}**.",
            "",
            f"**Evidence Quality:** {synthesis.evidence_quality.value.title()}",
            "",
            "**Key Findings:**",
        ]
        for i, finding in enumerate(synthesis.key_findings, 1):
            narrative_parts.append(f"{i}. {finding}")

        if synthesis.frameworks:
            narrative_parts.append("")
            narrative_parts.append("**Relevant Frameworks:**")
            for fw in synthesis.frameworks:
                narrative_parts.append(f"- {fw}")

        if synthesis.practical_applications:
            narrative_parts.append("")
            narrative_parts.append("**Practical Applications:**")
            for app in synthesis.practical_applications:
                narrative_parts.append(f"- {app}")

        if synthesis.caveats:
            narrative_parts.append("")
            narrative_parts.append("**Caveats:**")
            for caveat in synthesis.caveats:
                narrative_parts.append(f"- {caveat}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SAGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "synthesis": synthesis.model_dump(),
            },
            confidence=0.80,
            reasoning=f"Research synthesized on '{topic}' (evidence: {synthesis.evidence_quality.value})",
        )

    async def _executive_briefing(self, task: AgentTask) -> AgentResult:
        """Build an executive-ready briefing."""
        topic = task.parameters.get("topic")
        findings = task.parameters.get("findings")

        if not topic:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SAGE,
                status=TaskStatus.FAILED,
                output={"error": "topic is required"},
                confidence=0.0,
            )

        briefing = build_executive_briefing(topic, findings)

        # Build narrative
        narrative_parts = [
            f"# {briefing.title}",
            "",
            briefing.summary,
            "",
            "**Key Points:**",
        ]
        for point in briefing.key_points:
            narrative_parts.append(f"- {point}")

        narrative_parts.append("")
        narrative_parts.append("**Recommendations:**")
        for rec in briefing.recommendations:
            narrative_parts.append(f"- {rec}")

        if briefing.risks:
            narrative_parts.append("")
            narrative_parts.append("**Risks to Consider:**")
            for risk in briefing.risks:
                narrative_parts.append(f"- {risk}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SAGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "briefing": briefing.model_dump(),
            },
            confidence=0.82,
            reasoning=f"Executive briefing built on '{topic}'",
        )

    async def _knowledge_search(self, task: AgentTask) -> AgentResult:
        """Search organizational knowledge base via vector similarity."""
        query = task.parameters.get("query")
        collection = task.parameters.get("collection")

        if not query:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SAGE,
                status=TaskStatus.FAILED,
                output={"error": "query is required"},
                confidence=0.0,
            )

        results = search_knowledge_base(query, collection)

        if not results:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SAGE,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        f"No results found for '{query}' in the knowledge base. "
                        "The knowledge base may not yet contain relevant documents, "
                        "or the query may need to be rephrased."
                    ),
                    "response": (
                        f"I searched the knowledge base for '{query}' but didn't "
                        "find matching documents. Try broadening your search terms "
                        "or check that relevant documents have been uploaded."
                    ),
                    "results": [],
                    "result_count": 0,
                },
                confidence=0.70,
                reasoning="No matching documents found in knowledge base",
            )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SAGE,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Found {len(results)} relevant documents for '{query}'.",
                "response": (
                    f"I found {len(results)} documents relevant to your query. "
                    "Here are the most relevant results."
                ),
                "results": results,
                "result_count": len(results),
            },
            confidence=0.85,
            reasoning=f"Knowledge base search returned {len(results)} results",
        )
