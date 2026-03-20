from __future__ import annotations

"""Tests for SentinelIntegration — real-time compliance checking."""

import pytest
from unittest.mock import patch

from ai.meridian.rules.sentinel_integration import (
    SentinelIntegration,
    CompliancePolicy,
    ComplianceCheckResult,
    AuditEntry,
)
from ai.meridian.core.types import AgentId


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sentinel() -> SentinelIntegration:
    return SentinelIntegration()


# ---------------------------------------------------------------------------
# check_compliance — clean content
# ---------------------------------------------------------------------------

class TestCheckComplianceClean:

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_clean_content_is_compliant(self, mock_logger, sentinel):
        result = await sentinel.check_compliance(
            agent_id=AgentId.ECHO,
            action="general_analysis",
            content="The user shows strong communication skills and adaptability.",
        )

        assert isinstance(result, ComplianceCheckResult)
        assert result.is_compliant is True
        assert len(result.violations) == 0
        assert len(result.warnings) == 0


# ---------------------------------------------------------------------------
# check_compliance — EEOC
# ---------------------------------------------------------------------------

class TestCheckComplianceEEOC:

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_eeoc_sensitive_in_hiring_context(self, mock_logger, sentinel):
        result = await sentinel.check_compliance(
            agent_id=AgentId.NOVA,
            action="candidate screening",
            content="The candidate's age and national origin should be considered.",
        )

        assert result.is_compliant is True  # warnings, not violations
        assert len(result.warnings) > 0
        assert any("EEOC" in w for w in result.warnings)

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_eeoc_sensitive_not_hiring_no_warning(self, mock_logger, sentinel):
        """EEOC terms in non-hiring context should not trigger warnings."""
        result = await sentinel.check_compliance(
            agent_id=AgentId.ECHO,
            action="general_analysis",
            content="Discussion about age demographics in a research paper.",
        )

        eeoc_warnings = [w for w in result.warnings if "EEOC" in w]
        assert len(eeoc_warnings) == 0


# ---------------------------------------------------------------------------
# check_compliance — ADA
# ---------------------------------------------------------------------------

class TestCheckComplianceADA:

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_ada_sensitive_terms(self, mock_logger, sentinel):
        result = await sentinel.check_compliance(
            agent_id=AgentId.ATLAS,
            action="policy_review",
            content="The employee has a disability and needs accommodation.",
        )

        assert len(result.warnings) > 0
        assert any("ADA" in w for w in result.warnings)
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# check_compliance — GDPR
# ---------------------------------------------------------------------------

class TestCheckComplianceGDPR:

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_gdpr_sensitive_terms(self, mock_logger, sentinel):
        result = await sentinel.check_compliance(
            agent_id=AgentId.SENTINEL,
            action="data_review",
            content="We need consent for personal data processing and cross-border transfer.",
        )

        assert len(result.warnings) > 0
        assert any("GDPR" in w for w in result.warnings)
        assert len(result.recommendations) > 0


# ---------------------------------------------------------------------------
# record_audit
# ---------------------------------------------------------------------------

class TestRecordAudit:

    @patch("ai.meridian.rules.sentinel_integration.logger")
    def test_record_audit_adds_entry(self, mock_logger, sentinel):
        audit_id = sentinel.record_audit(
            agent_id=AgentId.NOVA,
            action="candidate_ranking",
            input_summary="Ranked 5 candidates",
            output_summary="Top 3 selected",
            user_id="u1",
            organization_id="org_1",
        )

        assert isinstance(audit_id, str)
        trail = sentinel.get_audit_trail()
        assert len(trail) == 1
        assert trail[0].agent_id == AgentId.NOVA
        assert trail[0].action == "candidate_ranking"
        assert trail[0].user_id == "u1"

    @patch("ai.meridian.rules.sentinel_integration.logger")
    def test_record_audit_with_compliance_check(self, mock_logger, sentinel):
        check = ComplianceCheckResult(
            agent_id=AgentId.NOVA,
            policies_checked=[CompliancePolicy.EEOC],
            is_compliant=True,
        )
        audit_id = sentinel.record_audit(
            agent_id=AgentId.NOVA,
            action="hire",
            input_summary="input",
            output_summary="output",
            compliance_check=check,
        )

        trail = sentinel.get_audit_trail()
        assert trail[0].compliance_check is not None
        assert trail[0].compliance_check.is_compliant is True


# ---------------------------------------------------------------------------
# get_audit_trail with filters
# ---------------------------------------------------------------------------

class TestGetAuditTrail:

    @patch("ai.meridian.rules.sentinel_integration.logger")
    def test_filter_by_agent_id(self, mock_logger, sentinel):
        sentinel.record_audit(AgentId.NOVA, "a1", "i", "o")
        sentinel.record_audit(AgentId.ECHO, "a2", "i", "o")
        sentinel.record_audit(AgentId.NOVA, "a3", "i", "o")

        trail = sentinel.get_audit_trail(agent_id=AgentId.NOVA)
        assert len(trail) == 2
        assert all(e.agent_id == AgentId.NOVA for e in trail)

    @patch("ai.meridian.rules.sentinel_integration.logger")
    def test_filter_by_organization_id(self, mock_logger, sentinel):
        sentinel.record_audit(AgentId.NOVA, "a1", "i", "o", organization_id="org_1")
        sentinel.record_audit(AgentId.NOVA, "a2", "i", "o", organization_id="org_2")

        trail = sentinel.get_audit_trail(organization_id="org_1")
        assert len(trail) == 1

    @patch("ai.meridian.rules.sentinel_integration.logger")
    def test_limit(self, mock_logger, sentinel):
        for i in range(5):
            sentinel.record_audit(AgentId.ECHO, f"a{i}", "i", "o")

        trail = sentinel.get_audit_trail(limit=3)
        assert len(trail) == 3


# ---------------------------------------------------------------------------
# configure_org_policies
# ---------------------------------------------------------------------------

class TestConfigureOrgPolicies:

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_org_policies_limit_checks(self, mock_logger, sentinel):
        """When org is configured with only GDPR, EEOC checks should not run."""
        sentinel.configure_org_policies("org_eu", [CompliancePolicy.GDPR])

        result = await sentinel.check_compliance(
            agent_id=AgentId.NOVA,
            action="candidate screening",
            content="The candidate's age and national origin plus personal data processing",
            organization_id="org_eu",
        )

        # Only GDPR should be checked
        assert CompliancePolicy.GDPR in result.policies_checked
        assert CompliancePolicy.EEOC not in result.policies_checked
        # GDPR warning should be present
        assert any("GDPR" in w for w in result.warnings)
        # EEOC warning should NOT be present
        eeoc_warnings = [w for w in result.warnings if "EEOC" in w]
        assert len(eeoc_warnings) == 0

    @pytest.mark.asyncio
    @patch("ai.meridian.rules.sentinel_integration.logger")
    async def test_unconfigured_org_checks_all_policies(self, mock_logger, sentinel):
        result = await sentinel.check_compliance(
            agent_id=AgentId.ECHO,
            action="general",
            content="disability accommodation and personal data consent",
        )

        # All policies checked by default
        assert len(result.policies_checked) == len(CompliancePolicy)
