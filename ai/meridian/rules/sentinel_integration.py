from __future__ import annotations

"""
Sentinel Integration — real-time compliance checking.

Sentinel (The Principled Advisor) provides:
- Pre-execution validation on all agent outputs
- Audit trail generation
- Policy mapping (EEOC, ADA, GDPR, SOC 2)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
from ai.meridian.core.types import AgentId
import uuid


class CompliancePolicy(str, Enum):
    """Supported compliance frameworks."""
    EEOC = "eeoc"       # Equal Employment Opportunity
    ADA = "ada"         # Americans with Disabilities Act
    GDPR = "gdpr"       # General Data Protection Regulation
    SOC2 = "soc2"       # Service Organization Control 2


class ComplianceCheckResult(BaseModel):
    """Result of a compliance check."""
    check_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentId
    policies_checked: list[CompliancePolicy]
    is_compliant: bool
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    """An entry in the audit trail."""
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: AgentId
    action: str
    input_summary: str
    output_summary: str
    compliance_check: Optional[ComplianceCheckResult] = None
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SentinelIntegration:
    """
    Real-time compliance checking integration for the Meridian system.

    Provides pre-execution validation on agent outputs, audit trail
    generation, and policy mapping for EEOC, ADA, GDPR, and SOC 2.
    """

    # Patterns that indicate potential compliance concerns
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

    def __init__(self) -> None:
        self._audit_trail: list[AuditEntry] = []
        # Per-organization policy configurations
        self._org_policies: dict[str, list[CompliancePolicy]] = {}

    def configure_org_policies(
        self, organization_id: str, policies: list[CompliancePolicy]
    ) -> None:
        """Configure which compliance policies apply to an organization."""
        self._org_policies[organization_id] = policies
        logger.info(
            f"SentinelIntegration: configured policies for org {organization_id}: "
            f"{[p.value for p in policies]}"
        )

    async def check_compliance(
        self,
        agent_id: AgentId,
        action: str,
        content: str,
        organization_id: Optional[str] = None,
    ) -> ComplianceCheckResult:
        """
        Pre-execution compliance check on agent output.

        Checks content against applicable compliance policies and returns
        violations, warnings, and recommendations.
        """
        # Determine applicable policies
        policies = self._get_applicable_policies(organization_id)
        violations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []
        content_lower = content.lower()

        for policy in policies:
            if policy == CompliancePolicy.EEOC:
                v, w, r = self._check_eeoc(content_lower, action)
                violations.extend(v)
                warnings.extend(w)
                recommendations.extend(r)

            elif policy == CompliancePolicy.ADA:
                v, w, r = self._check_ada(content_lower, action)
                violations.extend(v)
                warnings.extend(w)
                recommendations.extend(r)

            elif policy == CompliancePolicy.GDPR:
                v, w, r = self._check_gdpr(content_lower, action)
                violations.extend(v)
                warnings.extend(w)
                recommendations.extend(r)

            elif policy == CompliancePolicy.SOC2:
                v, w, r = self._check_soc2(content_lower, action)
                violations.extend(v)
                warnings.extend(w)
                recommendations.extend(r)

        result = ComplianceCheckResult(
            agent_id=agent_id,
            policies_checked=policies,
            is_compliant=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            recommendations=recommendations,
        )

        logger.info(
            f"SentinelIntegration: compliance check for {agent_id.value} — "
            f"compliant={result.is_compliant}, "
            f"violations={len(violations)}, warnings={len(warnings)}"
        )
        return result

    def record_audit(
        self,
        agent_id: AgentId,
        action: str,
        input_summary: str,
        output_summary: str,
        compliance_check: Optional[ComplianceCheckResult] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ) -> str:
        """
        Record an action in the audit trail.
        Returns the audit_id.
        """
        entry = AuditEntry(
            agent_id=agent_id,
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            compliance_check=compliance_check,
            user_id=user_id,
            organization_id=organization_id,
        )
        self._audit_trail.append(entry)
        logger.debug(f"SentinelIntegration: audit entry {entry.audit_id} recorded")
        return entry.audit_id

    def get_audit_trail(
        self,
        agent_id: Optional[AgentId] = None,
        organization_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Retrieve audit trail entries with optional filters."""
        entries = self._audit_trail
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if organization_id:
            entries = [e for e in entries if e.organization_id == organization_id]
        return entries[-limit:]

    def _get_applicable_policies(
        self, organization_id: Optional[str]
    ) -> list[CompliancePolicy]:
        """Get policies applicable to an organization (default: all)."""
        if organization_id and organization_id in self._org_policies:
            return self._org_policies[organization_id]
        return list(CompliancePolicy)

    def _check_eeoc(
        self, content: str, action: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Check for EEOC compliance concerns."""
        violations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        hiring_actions = ["hire", "interview", "candidate", "selection", "screening"]
        is_hiring = any(term in action.lower() for term in hiring_actions)

        found_terms = [
            term for term in self.EEOC_SENSITIVE_TERMS if term in content
        ]
        if found_terms and is_hiring:
            warnings.append(
                f"EEOC: Content references protected characteristics "
                f"({', '.join(found_terms)}) in a hiring context. "
                "Ensure decisions are based on job-related criteria."
            )
            recommendations.append(
                "Include PRISM behavioral data disclaimer and ensure "
                "assessment criteria are job-related and consistent."
            )
        return violations, warnings, recommendations

    def _check_ada(
        self, content: str, action: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Check for ADA compliance concerns."""
        violations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        found_terms = [
            term for term in self.ADA_SENSITIVE_TERMS if term in content
        ]
        if found_terms:
            warnings.append(
                f"ADA: Content references disability-related terms "
                f"({', '.join(found_terms)}). Ensure reasonable accommodations "
                "are considered."
            )
            recommendations.append(
                "Verify that any assessments or recommendations account "
                "for reasonable accommodations under ADA."
            )
        return violations, warnings, recommendations

    def _check_gdpr(
        self, content: str, action: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Check for GDPR compliance concerns."""
        violations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        found_terms = [
            term for term in self.GDPR_SENSITIVE_TERMS if term in content
        ]
        if found_terms:
            warnings.append(
                f"GDPR: Content involves personal data processing "
                f"({', '.join(found_terms)}). Ensure proper consent and "
                "data handling procedures."
            )
            recommendations.append(
                "Verify data subject consent, purpose limitation, "
                "and data minimization requirements are met."
            )
        return violations, warnings, recommendations

    def _check_soc2(
        self, content: str, action: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Check for SOC 2 compliance concerns."""
        violations: list[str] = []
        warnings: list[str] = []
        recommendations: list[str] = []

        security_terms = [
            "password", "credential", "api key", "secret", "token",
            "access control", "encryption",
        ]
        found_terms = [term for term in security_terms if term in content]
        if found_terms:
            warnings.append(
                f"SOC 2: Content references security-sensitive terms "
                f"({', '.join(found_terms)}). Ensure proper access controls."
            )
            recommendations.append(
                "Verify that sensitive data is encrypted and access "
                "is logged per SOC 2 requirements."
            )
        return violations, warnings, recommendations
