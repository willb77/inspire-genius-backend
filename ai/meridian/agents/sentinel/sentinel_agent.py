from __future__ import annotations

from typing import Any
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.sentinel.sentinel_prompts import (
    SENTINEL_SYSTEM_PROMPT,
    SENTINEL_DISCLAIMER_PROMPT,
)
from ai.meridian.agents.sentinel.sentinel_tools import (
    ComplianceReport,
    DecisionLog,
    HumanInLoopGate,
    PRISM_DISCLAIMER,
    check_content_compliance,
    log_decision,
    create_escalation_gate,
)
from prism_inspire.core.log_config import logger


class SentinelAgent(BaseAgent):
    """
    Sentinel — The Principled Advisor.

    Pre-execution compliance validation, audit trail generation,
    and human-in-the-loop escalation gating.

    Supported actions:
    - compliance_check: Pre-execution validation against EEOC/ADA/GDPR/SOC2
    - log_decision: Record a decision in the audit trail
    - escalation_gate: Create a human-in-the-loop gate
    - enforce_disclaimer: Attach PRISM disclaimer to employment outputs
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.SENTINEL)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._decision_log: list[DecisionLog] = []

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.SENTINEL,
            name="Sentinel",
            tagline="The Principled Advisor",
            domain=OrchestratorId.ORGANIZATIONAL_INTELLIGENCE,
            actions=[
                "compliance_check",
                "log_decision",
                "escalation_gate",
                "enforce_disclaimer",
            ],
            description=(
                "Provides pre-execution compliance validation, PRISM disclaimer "
                "enforcement, audit trail generation, and human-in-the-loop "
                "escalation gating for all Meridian agent outputs."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "compliance_check": self._compliance_check,
            "log_decision": self._log_decision,
            "escalation_gate": self._escalation_gate,
            "enforce_disclaimer": self._enforce_disclaimer,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SENTINEL,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Sentinel",
            )

        return await handler(task)

    async def _compliance_check(self, task: AgentTask) -> AgentResult:
        """Pre-execution compliance validation."""
        content = task.parameters.get("content", "")
        action = task.parameters.get("action", "")
        policies = task.parameters.get("policies")

        if not content:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SENTINEL,
                status=TaskStatus.FAILED,
                output={"error": "content is required for compliance check"},
                confidence=0.0,
            )

        report = check_content_compliance(content, action, policies)

        # Auto-log the compliance check
        entry = log_decision(
            agent_id=AgentId.SENTINEL.value,
            action=f"compliance_check:{action}",
            outcome=f"compliant={report.is_compliant}, warnings={len(report.warnings)}",
            is_compliant=report.is_compliant,
        )
        self._decision_log.append(entry)

        status_msg = "compliant" if report.is_compliant else "non-compliant"
        summary = (
            f"Compliance check: {status_msg}. "
            f"{len(report.warnings)} warning(s), {len(report.violations)} violation(s)."
        )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SENTINEL,
            status=TaskStatus.COMPLETED,
            output={
                "summary": summary,
                "response": summary,
                "compliance_report": report.model_dump(),
            },
            confidence=0.92,
            reasoning="Pre-execution compliance check completed",
        )

    async def _log_decision(self, task: AgentTask) -> AgentResult:
        """Record a decision in the audit trail."""
        agent_id = task.parameters.get("agent_id", "unknown")
        action = task.parameters.get("action", "")
        outcome = task.parameters.get("outcome", "")

        entry = log_decision(
            agent_id=agent_id,
            action=action,
            outcome=outcome,
            is_compliant=task.parameters.get("is_compliant", True),
        )
        self._decision_log.append(entry)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SENTINEL,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Decision logged: {entry.decision_id}",
                "response": f"Decision recorded in audit trail ({entry.decision_id}).",
                "decision_log": entry.model_dump(),
            },
            confidence=0.95,
            reasoning="Decision logged to audit trail",
        )

    async def _escalation_gate(self, task: AgentTask) -> AgentResult:
        """Create a human-in-the-loop escalation gate."""
        reason = task.parameters.get("reason", "")
        confidence = task.parameters.get("confidence", 0.0)

        if not reason:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.SENTINEL,
                status=TaskStatus.FAILED,
                output={"error": "reason is required for escalation gate"},
                confidence=0.0,
            )

        gate = create_escalation_gate(reason, confidence)

        logger.info(
            f"Sentinel: escalation gate created ({gate.gate_id}) — "
            f"reason: {reason}, confidence: {confidence:.2f}"
        )

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SENTINEL,
            status=TaskStatus.AWAITING_HUMAN,
            output={
                "summary": f"Escalation gate created: {gate.gate_id}",
                "response": (
                    f"This action requires human approval. Gate {gate.gate_id} "
                    f"created — reason: {reason}"
                ),
                "gate": gate.model_dump(),
            },
            confidence=confidence,
            reasoning=f"Human-in-the-loop gate created: {reason}",
        )

    async def _enforce_disclaimer(self, task: AgentTask) -> AgentResult:
        """Attach PRISM disclaimer to employment-related output."""
        content = task.parameters.get("content", "")

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.SENTINEL,
            status=TaskStatus.COMPLETED,
            output={
                "summary": "PRISM disclaimer enforced.",
                "response": content,
                "disclaimer": PRISM_DISCLAIMER,
                "full_disclaimer": SENTINEL_DISCLAIMER_PROMPT,
            },
            confidence=0.98,
            reasoning="PRISM employment disclaimer attached",
        )
