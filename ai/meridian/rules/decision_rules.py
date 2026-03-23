from __future__ import annotations

"""
Meridian Decision Rules Engine — configurable per-organization.

Handles:
- Confidence thresholds for autonomous vs. human-approval decisions
- Approval chains and escalation protocols
- Timeout settings for human-in-the-loop gates
- PRISM disclaimer enforcement
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
from ai.meridian.core.types import ConfidenceLevel, AgentId
import uuid


class EscalationAction(str, Enum):
    PROCEED = "proceed"
    LOG_AND_PROCEED = "log_and_proceed"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class DecisionRule(BaseModel):
    """A single decision rule for the engine."""
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    agent_id: Optional[AgentId] = None  # None = applies to all agents
    organization_id: Optional[str] = None  # None = global rule
    min_confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    action_below_threshold: EscalationAction = EscalationAction.REQUIRE_APPROVAL
    requires_sentinel_review: bool = False
    requires_prism_disclaimer: bool = False
    timeout_seconds: int = 3600  # 1 hour default for human-in-the-loop
    is_active: bool = True


class ApprovalRequest(BaseModel):
    """A request for human approval."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str
    agent_id: AgentId
    action_description: str
    confidence: float
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending, approved, denied, timed_out
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class DecisionOutcome(BaseModel):
    """The outcome of a decision evaluation."""
    action: EscalationAction
    confidence_level: ConfidenceLevel
    rule_applied: Optional[str] = None
    approval_request: Optional[ApprovalRequest] = None
    prism_disclaimer_required: bool = False
    sentinel_review_required: bool = False
    reason: str = ""


class DecisionRulesEngine:
    """
    Configurable decision rules engine for the Meridian system.

    Evaluates agent outputs against organizational rules to determine
    whether actions can proceed autonomously or require human approval.

    Key features:
    - Per-organization rule configuration
    - Confidence-based escalation (HIGH=auto, MEDIUM=log, LOW=human)
    - PRISM disclaimer enforcement
    - Approval chain management with timeouts
    """

    # Default rules applied when no org-specific rules exist
    DEFAULT_RULES: list[DecisionRule] = [
        DecisionRule(
            name="high_confidence_auto",
            description="Allow autonomous execution for high-confidence decisions",
            min_confidence=0.85,
            action_below_threshold=EscalationAction.REQUIRE_APPROVAL,
        ),
        DecisionRule(
            name="prism_employment_disclaimer",
            description="Require PRISM disclaimer for employment-related decisions",
            requires_prism_disclaimer=True,
            agent_id=AgentId.AURA,
        ),
        DecisionRule(
            name="sentinel_compliance_check",
            description="Require Sentinel review for compliance-sensitive actions",
            requires_sentinel_review=True,
            agent_id=AgentId.ATLAS,
        ),
        DecisionRule(
            name="hiring_human_review",
            description="Require human review for hiring decisions",
            min_confidence=0.95,
            action_below_threshold=EscalationAction.REQUIRE_APPROVAL,
            agent_id=AgentId.NOVA,
            requires_prism_disclaimer=True,
            requires_sentinel_review=True,
        ),
    ]

    PRISM_DISCLAIMER = (
        "PRISM behavioral assessment data provides insights into behavioral "
        "preferences and tendencies. This data should never be used as the "
        "sole basis for employment, promotion, termination, or other personnel "
        "decisions. All decisions must consider the full context of an "
        "individual's qualifications, experience, and performance."
    )

    def __init__(self) -> None:
        # Organization-specific rules: org_id -> list of rules
        self._org_rules: dict[str, list[DecisionRule]] = {}
        # Global rules (no org_id)
        self._global_rules: list[DecisionRule] = list(self.DEFAULT_RULES)
        # Pending approval requests
        self._pending_approvals: dict[str, ApprovalRequest] = {}

    def add_rule(self, rule: DecisionRule) -> None:
        """Add a decision rule. Org-specific if organization_id is set."""
        if rule.organization_id:
            if rule.organization_id not in self._org_rules:
                self._org_rules[rule.organization_id] = []
            self._org_rules[rule.organization_id].append(rule)
        else:
            self._global_rules.append(rule)
        logger.info(f"DecisionRulesEngine: added rule '{rule.name}'")

    def evaluate(
        self,
        agent_id: AgentId,
        confidence: float,
        action_description: str,
        organization_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> DecisionOutcome:
        """
        Evaluate an agent's proposed action against decision rules.

        Returns a DecisionOutcome specifying whether to proceed,
        require approval, or block.
        """
        # Gather applicable rules: org-specific + global
        rules = list(self._global_rules)
        if organization_id and organization_id in self._org_rules:
            rules.extend(self._org_rules[organization_id])

        # Filter to active rules relevant to this agent
        applicable = [
            r for r in rules
            if r.is_active and (r.agent_id is None or r.agent_id == agent_id)
        ]

        if not applicable:
            # No rules apply — default to confidence-based decision
            level = self._classify_confidence(confidence)
            return DecisionOutcome(
                action=EscalationAction.PROCEED if level == ConfidenceLevel.HIGH
                else EscalationAction.LOG_AND_PROCEED,
                confidence_level=level,
                reason="No specific rules apply; using default confidence thresholds",
            )

        # Apply the most restrictive matching rule
        most_restrictive = None
        for rule in applicable:
            if confidence < rule.min_confidence:
                if most_restrictive is None or self._escalation_severity(
                    rule.action_below_threshold
                ) > self._escalation_severity(
                    most_restrictive.action_below_threshold
                ):
                    most_restrictive = rule

        level = self._classify_confidence(confidence)

        # Check for PRISM disclaimer and Sentinel requirements
        prism_required = any(r.requires_prism_disclaimer for r in applicable)
        sentinel_required = any(r.requires_sentinel_review for r in applicable)

        if most_restrictive is None:
            return DecisionOutcome(
                action=EscalationAction.PROCEED,
                confidence_level=level,
                prism_disclaimer_required=prism_required,
                sentinel_review_required=sentinel_required,
                reason="All confidence thresholds met",
            )

        # Create approval request if needed
        approval = None
        if most_restrictive.action_below_threshold == EscalationAction.REQUIRE_APPROVAL:
            approval = ApprovalRequest(
                rule_id=most_restrictive.rule_id,
                agent_id=agent_id,
                action_description=action_description,
                confidence=confidence,
                context=context or {},
            )
            self._pending_approvals[approval.request_id] = approval

        return DecisionOutcome(
            action=most_restrictive.action_below_threshold,
            confidence_level=level,
            rule_applied=most_restrictive.name,
            approval_request=approval,
            prism_disclaimer_required=prism_required,
            sentinel_review_required=sentinel_required,
            reason=(
                f"Rule '{most_restrictive.name}' triggered: confidence "
                f"{confidence:.2f} < threshold {most_restrictive.min_confidence:.2f}"
            ),
        )

    def resolve_approval(
        self,
        request_id: str,
        approved: bool,
        resolved_by: str,
    ) -> Optional[ApprovalRequest]:
        """Resolve a pending approval request."""
        request = self._pending_approvals.pop(request_id, None)
        if request is None:
            return None
        request.status = "approved" if approved else "denied"
        request.resolved_at = datetime.utcnow()
        request.resolved_by = resolved_by
        logger.info(
            f"DecisionRulesEngine: approval {request_id} "
            f"{'approved' if approved else 'denied'} by {resolved_by}"
        )
        return request

    def get_pending_approvals(
        self, organization_id: Optional[str] = None
    ) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        approvals = list(self._pending_approvals.values())
        if organization_id:
            approvals = [
                a for a in approvals
                if a.context.get("organization_id") == organization_id
            ]
        return approvals

    def get_prism_disclaimer(self) -> str:
        """Return the PRISM behavioral data disclaimer text."""
        return self.PRISM_DISCLAIMER

    def _classify_confidence(self, confidence: float) -> ConfidenceLevel:
        if confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif confidence >= 0.60:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    @staticmethod
    def _escalation_severity(action: EscalationAction) -> int:
        return {
            EscalationAction.PROCEED: 0,
            EscalationAction.LOG_AND_PROCEED: 1,
            EscalationAction.REQUIRE_APPROVAL: 2,
            EscalationAction.BLOCK: 3,
        }.get(action, 0)
