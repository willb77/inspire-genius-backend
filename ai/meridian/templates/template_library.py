from __future__ import annotations

"""
Process Template Library — predefined multi-agent workflows.

Templates reduce LLM planning cost by ~50% and improve response consistency.
Each template defines a DAG of agent steps with dependency ordering.
"""

from typing import Any, Optional
from ai.meridian.core.types import (
    AgentId, AgentTask, DAGNode, ProcessTemplate, OrchestratorId,
)
from prism_inspire.core.log_config import logger


# ─────────────────────────────────────────────────────────────────────────────
# Template definitions
# ─────────────────────────────────────────────────────────────────────────────

PROCESS_TEMPLATES: dict[str, ProcessTemplate] = {

    "new_user_onboarding": ProcessTemplate(
        template_id="new_user_onboarding",
        name="New User Behavioral Preference Map Onboarding",
        description="Aura interprets PRISM → Nova explores career goals → Meridian synthesizes welcome",
        trigger_patterns=["new user", "onboarding", "first time", "just joined", "getting started", "welcome"],
        steps=[
            {"node_id": "aura_profile", "agent_id": "aura", "action": "interpret_profile", "deps": []},
            {"node_id": "nova_career", "agent_id": "nova", "action": "career_strategy", "deps": ["aura_profile"]},
        ],
    ),

    "behavioral_interview_prep": ProcessTemplate(
        template_id="behavioral_interview_prep",
        name="Behavioral Interview Preparation",
        description="Aura profile → James fit analysis → Nova strategy → Ascend presence → unified prep guide",
        trigger_patterns=["interview prep", "prepare for interview", "behavioral interview", "interview coming up"],
        steps=[
            {"node_id": "aura_profile", "agent_id": "aura", "action": "interpret_profile", "deps": []},
            {"node_id": "james_fit", "agent_id": "james", "action": "score_candidate", "deps": ["aura_profile"]},
            {"node_id": "nova_strategy", "agent_id": "nova", "action": "career_strategy", "deps": ["james_fit"]},
            {"node_id": "ascend_presence", "agent_id": "ascend", "action": "executive_coaching", "deps": ["aura_profile", "nova_strategy"]},
        ],
    ),

    "team_composition_analysis": ProcessTemplate(
        template_id="team_composition_analysis",
        name="Team Composition Analysis",
        description="Aura generates team behavioral context → Atlas analyzes composition and diversity",
        trigger_patterns=["team composition", "team analysis", "team diversity", "analyze my team"],
        steps=[
            {"node_id": "aura_context", "agent_id": "aura", "action": "generate_context", "deps": []},
            {"node_id": "atlas_analyze", "agent_id": "atlas", "action": "analyze_team", "deps": ["aura_context"]},
        ],
    ),

    "performance_review_prep": ProcessTemplate(
        template_id="performance_review_prep",
        name="Performance Review Preparation",
        description="Aura insights + Nova trajectory + Sentinel compliance + Nexus cultural context",
        trigger_patterns=["performance review", "review prep", "annual review", "review meeting"],
        steps=[
            {"node_id": "aura_insights", "agent_id": "aura", "action": "interpret_profile", "deps": []},
            {"node_id": "nova_trajectory", "agent_id": "nova", "action": "promotion_readiness", "deps": []},
            {"node_id": "sentinel_check", "agent_id": "sentinel", "action": "compliance_check", "deps": ["aura_insights", "nova_trajectory"]},
            {"node_id": "nexus_culture", "agent_id": "nexus", "action": "calibrate_style", "deps": ["aura_insights"]},
        ],
    ),

    "hiring_triage": ProcessTemplate(
        template_id="hiring_triage",
        name="Hiring & Interview Triage",
        description="Nova submits → James scores → James interview guide → Nova publishes",
        trigger_patterns=["hiring triage", "evaluate candidate", "candidate triage", "hiring pipeline"],
        steps=[
            {"node_id": "nova_submit", "agent_id": "nova", "action": "submit_candidate", "deps": []},
            {"node_id": "james_score", "agent_id": "james", "action": "score_candidate", "deps": ["nova_submit"]},
            {"node_id": "james_interview", "agent_id": "james", "action": "generate_interview_guide", "deps": ["james_score"]},
            {"node_id": "nova_publish", "agent_id": "nova", "action": "publish_triage", "deps": ["james_score", "james_interview"]},
        ],
    ),

    "executive_leadership_coaching": ProcessTemplate(
        template_id="executive_leadership_coaching",
        name="Executive Leadership Coaching",
        description="Aura behavioral profile → Ascend leadership analysis → Sage evidence-based frameworks",
        trigger_patterns=["executive coaching", "leadership coaching", "leadership development", "executive development"],
        steps=[
            {"node_id": "aura_profile", "agent_id": "aura", "action": "interpret_profile", "deps": []},
            {"node_id": "ascend_signature", "agent_id": "ascend", "action": "leadership_signature", "deps": ["aura_profile"]},
            {"node_id": "sage_evidence", "agent_id": "sage", "action": "research_synthesis", "deps": ["ascend_signature"]},
        ],
    ),

    "school_to_career_pipeline": ProcessTemplate(
        template_id="school_to_career_pipeline",
        name="School-to-Career Pipeline",
        description="Aura student profile → Alex exploration → Bridge matching → Echo learning paths → Sentinel compliance",
        trigger_patterns=["school to career", "student pipeline", "career pipeline", "student placement"],
        steps=[
            {"node_id": "aura_student", "agent_id": "aura", "action": "interpret_profile", "deps": []},
            {"node_id": "alex_explore", "agent_id": "alex", "action": "career_exploration", "deps": ["aura_student"]},
            {"node_id": "bridge_match", "agent_id": "bridge", "action": "match_student", "deps": ["alex_explore"]},
            {"node_id": "echo_learning", "agent_id": "echo", "action": "create_learning_path", "deps": ["alex_explore"]},
            {"node_id": "sentinel_ferpa", "agent_id": "sentinel", "action": "compliance_check", "deps": ["bridge_match"]},
        ],
    ),

    "resilience_checkin": ProcessTemplate(
        template_id="resilience_checkin",
        name="Resilience Check-In",
        description="Anchor stress check-in with Aura behavioral context for personalized recovery",
        trigger_patterns=["resilience check", "wellness check", "how am i doing", "check in on me", "burnout check"],
        steps=[
            {"node_id": "aura_context", "agent_id": "aura", "action": "generate_context", "deps": []},
            {"node_id": "anchor_checkin", "agent_id": "anchor", "action": "stress_checkin", "deps": ["aura_context"]},
        ],
    ),

    "conflict_resolution": ProcessTemplate(
        template_id="conflict_resolution",
        name="Conflict Resolution",
        description="Aura profiles both parties → Forge analyzes conflict dynamics and builds playbook",
        trigger_patterns=["resolve conflict", "conflict resolution", "having a disagreement", "difficult colleague"],
        steps=[
            {"node_id": "aura_user", "agent_id": "aura", "action": "generate_context", "deps": []},
            {"node_id": "forge_resolve", "agent_id": "forge", "action": "resolve_conflict", "deps": ["aura_user"]},
            {"node_id": "forge_playbook", "agent_id": "forge", "action": "communication_playbook", "deps": ["forge_resolve"]},
        ],
    ),
}


class TemplateLibrary:
    """
    Manages process templates and compiles them into executable DAGs.

    Template matching reduces LLM planning cost by ~50%: instead of asking
    the LLM to plan from scratch, we match known patterns and only use
    LLM planning for novel queries.
    """

    def __init__(self) -> None:
        self._templates: dict[str, ProcessTemplate] = dict(PROCESS_TEMPLATES)

    def register_template(self, template: ProcessTemplate) -> None:
        """Register a custom template (e.g., per-organization)."""
        self._templates[template.template_id] = template

    def match(self, user_input: str) -> Optional[ProcessTemplate]:
        """Match user input against template trigger patterns."""
        text = user_input.lower()
        best_match: Optional[ProcessTemplate] = None
        best_score = 0

        for template in self._templates.values():
            score = 0
            for pattern in template.trigger_patterns:
                if pattern.lower() in text:
                    # Longer pattern matches are more specific → higher score
                    score = max(score, len(pattern))
            if score > best_score:
                best_score = score
                best_match = template

        return best_match

    def compile_dag(
        self,
        template: ProcessTemplate,
        context: dict[str, Any],
    ) -> list[DAGNode]:
        """
        Compile a process template into an executable DAG.

        Each step in the template becomes a DAGNode with proper
        agent assignment, parameters, and dependency wiring.
        """
        user_id = context.get("user_id", "")
        behavioral_context = context.get("behavioral_context")
        parameters = context.get("parameters", {})

        nodes: list[DAGNode] = []
        for step in template.steps:
            agent_id = AgentId(step["agent_id"])
            node = DAGNode(
                node_id=step["node_id"],
                task=AgentTask(
                    agent_id=agent_id,
                    action=step["action"],
                    parameters={**parameters, "user_id": user_id, "template": template.template_id},
                    context=context,
                    behavioral_context=behavioral_context,
                ),
                dependencies=step.get("deps", []),
            )
            nodes.append(node)

        logger.info(
            f"TemplateLibrary: compiled '{template.template_id}' → "
            f"{len(nodes)} nodes"
        )
        return nodes

    def get_template(self, template_id: str) -> Optional[ProcessTemplate]:
        """Get a template by ID."""
        return self._templates.get(template_id)

    def list_templates(self) -> list[dict[str, Any]]:
        """List all available templates for admin views."""
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "trigger_patterns": t.trigger_patterns,
                "step_count": len(t.steps),
                "agents_involved": list({s["agent_id"] for s in t.steps}),
            }
            for t in self._templates.values()
        ]

    @property
    def template_count(self) -> int:
        return len(self._templates)
