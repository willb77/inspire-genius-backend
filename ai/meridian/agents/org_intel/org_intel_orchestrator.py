from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.orchestrator import BaseOrchestrator
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, DAGNode,
    OrchestratorId, TaskStatus,
)
from prism_inspire.core.log_config import logger


class OrgIntelOrchestrator(BaseOrchestrator):
    """
    Organizational Intelligence Orchestrator.
    Manages Atlas, Sentinel, Nexus, Bridge.
    """

    def __init__(self) -> None:
        super().__init__(OrchestratorId.ORGANIZATIONAL_INTELLIGENCE)

    async def plan(self, intent: str, context: dict) -> list[DAGNode]:
        user_id = context.get("user_id")
        behavioral_context = context.get("behavioral_context")
        params = context.get("parameters", {})
        text = intent.lower()

        # Sentinel — compliance, audit, policy, disclaimer
        if any(kw in text for kw in [
            "compliance", "audit", "eeoc", "ada", "gdpr", "soc", "policy",
            "disclaimer", "escalat", "approval",
        ]):
            action = "compliance_check"
            if any(kw in text for kw in ["log", "audit trail", "decision"]):
                action = "log_decision"
            elif any(kw in text for kw in ["escalat", "approval", "gate"]):
                action = "escalation_gate"
            elif any(kw in text for kw in ["disclaimer", "prism disclaimer"]):
                action = "enforce_disclaimer"
            return [DAGNode(task=AgentTask(
                agent_id=AgentId.SENTINEL, action=action,
                parameters={**params, "query": intent},
                context=context, behavioral_context=behavioral_context,
            ))]

        # Bridge — pipeline, school, student pipeline, employer pipeline, placement
        if any(kw in text for kw in [
            "pipeline", "school", "placement", "intern", "employer match",
            "talent pipeline", "curriculum", "student match",
        ]):
            action = "pipeline_health"
            if any(kw in text for kw in ["match", "student"]):
                action = "match_student"
            elif any(kw in text for kw in ["forecast", "employer"]):
                action = "employer_forecast"
            elif any(kw in text for kw in ["placement", "track"]):
                action = "assess_placement"
            return [DAGNode(task=AgentTask(
                agent_id=AgentId.BRIDGE, action=action,
                parameters={**params, "query": intent},
                context=context, behavioral_context=behavioral_context,
            ))]

        # Nexus — culture, language, cross-cultural, international
        if any(kw in text for kw in [
            "culture", "cultural", "language", "international", "cross-cultural",
            "hofstede", "localization", "translation", "global",
        ]):
            action = "cultural_profile"
            if any(kw in text for kw in ["adapt", "communication", "style"]):
                action = "adapt_communication"
            elif any(kw in text for kw in ["calibrat", "meridian style"]):
                action = "calibrate_style"
            return [DAGNode(task=AgentTask(
                agent_id=AgentId.NEXUS, action=action,
                parameters={**params, "query": intent},
                context=context, behavioral_context=behavioral_context,
            ))]

        # Atlas — team, organization, workforce, composition, talent optimizer
        if any(kw in text for kw in [
            "team", "organization", "workforce", "composition", "talent",
            "diversity", "restructur", "headcount",
        ]):
            action = "analyze_team"
            if any(kw in text for kw in ["workforce", "plan", "gap"]):
                action = "workforce_plan"
            elif any(kw in text for kw in ["optimizer", "score", "diversity"]):
                action = "talent_optimizer"
            return [DAGNode(task=AgentTask(
                agent_id=AgentId.ATLAS, action=action,
                parameters={**params, "query": intent},
                context=context, behavioral_context=behavioral_context,
            ))]

        # Multi-agent: Team Composition Analysis (Atlas + Aura)
        if "team analysis" in text or "composition analysis" in text:
            aura_node = DAGNode(
                node_id="aura_context",
                task=AgentTask(
                    agent_id=AgentId.AURA, action="generate_context",
                    parameters={"user_id": user_id, "requesting_agent": "atlas"},
                    context=context, behavioral_context=behavioral_context,
                ),
            )
            atlas_node = DAGNode(
                node_id="atlas_analyze",
                task=AgentTask(
                    agent_id=AgentId.ATLAS, action="analyze_team",
                    parameters=params, context=context, behavioral_context=behavioral_context,
                ),
                dependencies=["aura_context"],
            )
            return [aura_node, atlas_node]

        # Default: Atlas analyze_team
        return [DAGNode(task=AgentTask(
            agent_id=AgentId.ATLAS, action="analyze_team",
            parameters={**params, "query": intent},
            context=context, behavioral_context=behavioral_context,
        ))]
