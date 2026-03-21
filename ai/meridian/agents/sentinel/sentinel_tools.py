from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sensitive-term patterns (reused from sentinel_integration.py)
# ---------------------------------------------------------------------------

EEOC_SENSITIVE_TERMS = [
    "race", "color", "religion", "sex", "national origin", "age",
    "disability", "genetic information", "pregnancy", "gender identity",
]
ADA_SENSITIVE_TERMS = [
    "disability", "accommodation", "impairment", "medical condition",
    "physical limitation", "mental health",
]
GDPR_SENSITIVE_TERMS = [
    "personal data", "data subject", "consent", "right to be forgotten",
    "data processing", "cross-border transfer",
]
SOC2_SENSITIVE_TERMS = [
    "password", "credential", "api key", "secret", "token",
    "access control", "encryption",
]

PRISM_DISCLAIMER = (
    "PRISM behavioral preference data reflects self-reported behavioral "
    "tendencies and should not be used as the sole basis for any employment "
    "decision. All personnel decisions must comply with applicable employment "
    "laws and regulations."
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ComplianceReport(BaseModel):
    """Result of a compliance check."""
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policies_checked: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    is_compliant: bool = True
    recommendations: list[str] = Field(default_factory=list)


class DecisionLog(BaseModel):
    """An entry in the decision audit trail."""
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    action: str
    outcome: str
    compliance_status: str = "compliant"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HumanInLoopGate(BaseModel):
    """A gate requiring human approval before execution proceeds."""
    gate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reason: str
    confidence: float = 0.0
    status: str = "pending"  # pending | approved | denied


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def check_content_compliance(
    content: str,
    action: str,
    policies: Optional[list[str]] = None,
) -> ComplianceReport:
    """
    Check content against compliance policies.

    Scans for sensitive terms in the context of the given action and returns
    violations, warnings, and recommendations.
    """
    active_policies = policies or ["eeoc", "ada", "gdpr", "soc2"]
    content_lower = content.lower()
    action_lower = action.lower()

    violations: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    hiring_terms = ["hire", "interview", "candidate", "selection", "screening"]
    is_hiring = any(t in action_lower for t in hiring_terms)

    if "eeoc" in active_policies:
        found = [t for t in EEOC_SENSITIVE_TERMS if t in content_lower]
        if found and is_hiring:
            warnings.append(
                f"EEOC: References protected characteristics ({', '.join(found)}) "
                "in a hiring context. Ensure decisions are job-related."
            )
            recommendations.append("Include PRISM behavioral data disclaimer.")

    if "ada" in active_policies:
        found = [t for t in ADA_SENSITIVE_TERMS if t in content_lower]
        if found:
            warnings.append(
                f"ADA: References disability-related terms ({', '.join(found)}). "
                "Ensure reasonable accommodations are considered."
            )

    if "gdpr" in active_policies:
        found = [t for t in GDPR_SENSITIVE_TERMS if t in content_lower]
        if found:
            warnings.append(
                f"GDPR: Involves personal data processing ({', '.join(found)}). "
                "Verify consent and data handling."
            )

    if "soc2" in active_policies:
        found = [t for t in SOC2_SENSITIVE_TERMS if t in content_lower]
        if found:
            warnings.append(
                f"SOC 2: References security-sensitive terms ({', '.join(found)}). "
                "Ensure proper access controls."
            )

    return ComplianceReport(
        policies_checked=active_policies,
        violations=violations,
        warnings=warnings,
        is_compliant=len(violations) == 0,
        recommendations=recommendations,
    )


def log_decision(
    agent_id: str,
    action: str,
    outcome: str,
    is_compliant: bool = True,
) -> DecisionLog:
    """Create an audit trail entry for a decision."""
    return DecisionLog(
        agent_id=agent_id,
        action=action,
        outcome=outcome,
        compliance_status="compliant" if is_compliant else "non-compliant",
    )


def create_escalation_gate(
    reason: str,
    confidence: float,
) -> HumanInLoopGate:
    """Create a human-in-the-loop escalation gate."""
    return HumanInLoopGate(
        reason=reason,
        confidence=confidence,
        status="pending",
    )
