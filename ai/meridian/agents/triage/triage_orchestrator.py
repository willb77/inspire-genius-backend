from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.orchestrator import BaseOrchestrator
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, DAGNode,
    OrchestratorId, TaskStatus,
)
from prism_inspire.core.log_config import logger


class HiringTriageOrchestrator(BaseOrchestrator):
    """
    Orchestrates the Nova-James Hiring & Interview Triage Process.

    Full workflow (Section 4.4.1):
    1. Nova receives candidate submission -> triggers PRISM Light assessment
    2. James scores PRISM Light results against target Job Blueprint
    3. James classifies candidate into triage tier with evidence
    4. James generates hiring manager insight package
    5. Nova publishes results to hiring dashboard
    6. Human hiring manager makes final decision
    """

    def __init__(self) -> None:
        super().__init__(OrchestratorId.STRATEGIC_ADVISORY)

    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        """
        Build a DAG based on the intent type.

        Supports:
        - Hiring/triage/candidate queries -> multi-step Nova-James workflow
        - Career strategy/promotion queries -> Nova single-agent
        - Blueprint/scoring queries -> James single-agent
        """
        text = intent.lower()
        user_id = context.get("user_id")
        behavioral_context = context.get("behavioral_context")

        # Full triage workflow
        if any(kw in text for kw in ["triage", "evaluate candidate", "hiring pipeline"]):
            return self._plan_full_triage(context, behavioral_context)

        # Candidate submission
        if any(kw in text for kw in ["submit candidate", "new candidate", "candidate submission"]):
            task = AgentTask(
                agent_id=AgentId.NOVA,
                action="submit_candidate",
                parameters=context.get("parameters", {}),
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Job Blueprint creation
        if any(kw in text for kw in ["blueprint", "job blueprint", "create role", "define role"]):
            task = AgentTask(
                agent_id=AgentId.JAMES,
                action="create_blueprint",
                parameters=context.get("parameters", {}),
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Score candidate
        if any(kw in text for kw in ["score candidate", "fit score", "fit analysis", "match candidate"]):
            task = AgentTask(
                agent_id=AgentId.JAMES,
                action="score_candidate",
                parameters=context.get("parameters", {}),
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Interview guide
        if any(kw in text for kw in ["interview", "interview guide", "interview questions"]):
            task = AgentTask(
                agent_id=AgentId.JAMES,
                action="generate_interview_guide",
                parameters=context.get("parameters", {}),
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Career strategy (default for career/promotion keywords)
        if any(kw in text for kw in ["career", "promotion", "career path", "next role"]):
            task = AgentTask(
                agent_id=AgentId.NOVA,
                action="career_strategy",
                parameters={"user_id": user_id},
                context=context,
                behavioral_context=behavioral_context,
            )
            return [DAGNode(task=task)]

        # Default: career strategy
        task = AgentTask(
            agent_id=AgentId.NOVA,
            action="career_strategy",
            parameters={"user_id": user_id},
            context=context,
            behavioral_context=behavioral_context,
        )
        return [DAGNode(task=task)]

    def _plan_full_triage(
        self, context: dict, behavioral_context: Optional[dict]
    ) -> list[DAGNode]:
        """
        Build the full Nova-James triage DAG:

        Step 1 (Nova): Submit candidate, trigger PRISM Light
        Step 2 (James): Score PRISM results against Job Blueprint
        Step 3 (James): Generate interview guide
        Step 4 (Nova): Publish triage results to dashboard

        DAG:
          [Nova: submit] -> [James: score] -> [James: interview] -> [Nova: publish]
        """
        params = context.get("parameters", {})

        # Node 1: Nova submits candidate
        node1_id = "nova_submit"
        node1 = DAGNode(
            node_id=node1_id,
            task=AgentTask(
                agent_id=AgentId.NOVA,
                action="submit_candidate",
                parameters=params,
                context=context,
                behavioral_context=behavioral_context,
            ),
            dependencies=[],
        )

        # Node 2: James scores candidate
        node2_id = "james_score"
        node2 = DAGNode(
            node_id=node2_id,
            task=AgentTask(
                agent_id=AgentId.JAMES,
                action="score_candidate",
                parameters=params,
                context=context,
                behavioral_context=behavioral_context,
            ),
            dependencies=[node1_id],
        )

        # Node 3: James generates interview guide
        node3_id = "james_interview"
        node3 = DAGNode(
            node_id=node3_id,
            task=AgentTask(
                agent_id=AgentId.JAMES,
                action="generate_interview_guide",
                parameters=params,
                context=context,
                behavioral_context=behavioral_context,
            ),
            dependencies=[node2_id],
        )

        # Node 4: Nova publishes triage results
        node4_id = "nova_publish"
        node4 = DAGNode(
            node_id=node4_id,
            task=AgentTask(
                agent_id=AgentId.NOVA,
                action="publish_triage",
                parameters=params,
                context=context,
                behavioral_context=behavioral_context,
            ),
            dependencies=[node2_id, node3_id],
        )

        return [node1, node2, node3, node4]
