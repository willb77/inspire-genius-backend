from __future__ import annotations

"""
Admin Configuration — organization-level and user-level settings.

Configurable per Ecosystem Guide Section 3.2:
- Organization: decision rules, confidence thresholds, approval chains
- User: communication style, agent preferences
- HR Director: company-specific guardrails
"""

from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


class OrgConfig(BaseModel):
    """Organization-level configuration."""
    org_id: str
    name: str = ""
    # Decision rules
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    require_sentinel_review: bool = True
    require_prism_disclaimer: bool = True
    # Approval chains
    hiring_approval_required: bool = True
    hiring_approvers: list[str] = Field(default_factory=list)
    escalation_timeout_minutes: int = 60
    # Feature flags
    enable_voice: bool = False
    enable_bridge_pipeline: bool = False
    enable_alex_student: bool = False
    # Compliance
    compliance_policies: list[str] = Field(
        default_factory=lambda: ["eeoc", "ada", "gdpr", "soc2"]
    )
    # Agent restrictions
    disabled_agents: list[str] = Field(default_factory=list)
    # Custom guardrails (HR Director)
    custom_guardrails: list[str] = Field(default_factory=list)
    max_requests_per_user_per_day: int = 1000


class UserConfig(BaseModel):
    """User-level configuration and preferences."""
    user_id: str
    # Communication
    language: str = "en"
    formality: str = "professional"
    depth: str = "standard"
    encouragement_style: str = "balanced"
    voice_enabled: bool = False
    voice_id: str = "coral"
    # Focus
    focus_areas: list[str] = Field(default_factory=list)
    # Agent preferences
    preferred_agents: list[str] = Field(default_factory=list)
    disabled_agents: list[str] = Field(default_factory=list)


class AdminConfig:
    """
    Manages organization-level and user-level configuration.
    """

    def __init__(self) -> None:
        self._org_configs: dict[str, OrgConfig] = {}
        self._user_configs: dict[str, UserConfig] = {}

    # --- Organization ---

    def set_org_config(self, config: OrgConfig) -> None:
        """Set or update organization configuration."""
        self._org_configs[config.org_id] = config
        logger.info(f"AdminConfig: org '{config.org_id}' configured")

    def get_org_config(self, org_id: str) -> OrgConfig:
        """Get organization config (returns defaults if not configured)."""
        return self._org_configs.get(org_id, OrgConfig(org_id=org_id))

    def is_agent_enabled(self, org_id: str, agent_id: str) -> bool:
        """Check if an agent is enabled for an organization."""
        config = self.get_org_config(org_id)
        return agent_id not in config.disabled_agents

    def get_confidence_threshold(self, org_id: str) -> float:
        """Get the confidence threshold for autonomous decisions."""
        return self.get_org_config(org_id).confidence_threshold

    def get_compliance_policies(self, org_id: str) -> list[str]:
        """Get active compliance policies for an organization."""
        return self.get_org_config(org_id).compliance_policies

    # --- User ---

    def set_user_config(self, config: UserConfig) -> None:
        """Set or update user configuration."""
        self._user_configs[config.user_id] = config
        logger.info(f"AdminConfig: user '{config.user_id}' configured")

    def get_user_config(self, user_id: str) -> UserConfig:
        """Get user config (returns defaults if not configured)."""
        return self._user_configs.get(user_id, UserConfig(user_id=user_id))

    # --- HR Director Guardrails ---

    def set_guardrails(self, org_id: str, guardrails: list[str]) -> None:
        """Set company-specific guardrails (HR Director function)."""
        config = self.get_org_config(org_id)
        config.custom_guardrails = guardrails
        self._org_configs[org_id] = config
        logger.info(f"AdminConfig: guardrails set for org '{org_id}': {len(guardrails)} rules")

    def get_guardrails(self, org_id: str) -> list[str]:
        """Get company-specific guardrails."""
        return self.get_org_config(org_id).custom_guardrails

    # --- Summary ---

    def get_config_summary(self) -> dict[str, Any]:
        """Get summary for admin dashboard."""
        return {
            "organizations_configured": len(self._org_configs),
            "users_configured": len(self._user_configs),
            "orgs": {oid: c.model_dump() for oid, c in self._org_configs.items()},
        }
