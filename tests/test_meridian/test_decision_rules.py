from __future__ import annotations

"""Tests for DecisionRulesEngine — configurable decision rules."""

import pytest
from unittest.mock import patch

from ai.meridian.rules.decision_rules import (
    DecisionRulesEngine,
    DecisionRule,
    EscalationAction,
    ApprovalRequest,
    DecisionOutcome,
)
from ai.meridian.core.types import AgentId, ConfidenceLevel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> DecisionRulesEngine:
    return DecisionRulesEngine()


# ---------------------------------------------------------------------------
# evaluate()
# ---------------------------------------------------------------------------

class TestEvaluate:

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_high_confidence_returns_proceed(self, mock_logger, engine):
        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.95,
            action_description="Generate personality summary",
        )

        assert outcome.action == EscalationAction.PROCEED
        assert outcome.confidence_level == ConfidenceLevel.HIGH

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_low_confidence_triggers_require_approval(self, mock_logger, engine):
        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.50,
            action_description="Uncertain recommendation",
        )

        assert outcome.action == EscalationAction.REQUIRE_APPROVAL
        assert outcome.confidence_level == ConfidenceLevel.LOW
        assert outcome.approval_request is not None

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_agent_specific_rules_applied(self, mock_logger, engine):
        """Nova's hiring_human_review rule has min_confidence=0.95."""
        outcome = engine.evaluate(
            agent_id=AgentId.NOVA,
            confidence=0.90,
            action_description="Recommend candidate",
        )

        # 0.90 < 0.95 threshold for Nova's hiring_human_review
        assert outcome.action == EscalationAction.REQUIRE_APPROVAL
        assert outcome.rule_applied == "hiring_human_review"
        assert outcome.prism_disclaimer_required is True
        assert outcome.sentinel_review_required is True

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_nova_high_confidence_proceeds(self, mock_logger, engine):
        """Nova with confidence >= 0.95 meets all thresholds."""
        outcome = engine.evaluate(
            agent_id=AgentId.NOVA,
            confidence=0.96,
            action_description="Recommend candidate",
        )

        assert outcome.action == EscalationAction.PROCEED


# ---------------------------------------------------------------------------
# add_rule()
# ---------------------------------------------------------------------------

class TestAddRule:

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_add_org_specific_rule(self, mock_logger, engine):
        rule = DecisionRule(
            name="org_strict_review",
            description="Strict review for org X",
            organization_id="org_x",
            min_confidence=0.99,
            action_below_threshold=EscalationAction.BLOCK,
        )
        engine.add_rule(rule)

        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.90,
            action_description="Test action",
            organization_id="org_x",
        )

        assert outcome.action == EscalationAction.BLOCK

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_add_global_rule(self, mock_logger, engine):
        rule = DecisionRule(
            name="extra_global",
            description="Extra global check",
            min_confidence=0.99,
            action_below_threshold=EscalationAction.BLOCK,
        )
        engine.add_rule(rule)

        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.90,
            action_description="Test",
        )

        assert outcome.action == EscalationAction.BLOCK


# ---------------------------------------------------------------------------
# resolve_approval()
# ---------------------------------------------------------------------------

class TestResolveApproval:

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_resolve_approval_approved(self, mock_logger, engine):
        # Trigger an approval request
        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.50,
            action_description="Low confidence action",
        )
        assert outcome.approval_request is not None
        request_id = outcome.approval_request.request_id

        resolved = engine.resolve_approval(request_id, approved=True, resolved_by="admin")

        assert resolved is not None
        assert resolved.status == "approved"
        assert resolved.resolved_by == "admin"
        assert resolved.resolved_at is not None

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_resolve_approval_denied(self, mock_logger, engine):
        outcome = engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.50,
            action_description="Low confidence action",
        )
        request_id = outcome.approval_request.request_id

        resolved = engine.resolve_approval(request_id, approved=False, resolved_by="mgr")

        assert resolved.status == "denied"

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_resolve_unknown_returns_none(self, mock_logger, engine):
        result = engine.resolve_approval("nonexistent_id", approved=True, resolved_by="x")
        assert result is None


# ---------------------------------------------------------------------------
# get_pending_approvals()
# ---------------------------------------------------------------------------

class TestGetPendingApprovals:

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_get_pending(self, mock_logger, engine):
        engine.evaluate(
            agent_id=AgentId.ECHO,
            confidence=0.50,
            action_description="Action 1",
        )
        engine.evaluate(
            agent_id=AgentId.FORGE,
            confidence=0.40,
            action_description="Action 2",
        )

        approvals = engine.get_pending_approvals()
        assert len(approvals) == 2

    @patch("ai.meridian.rules.decision_rules.logger")
    def test_get_pending_empty(self, mock_logger, engine):
        assert engine.get_pending_approvals() == []


# ---------------------------------------------------------------------------
# PRISM disclaimer
# ---------------------------------------------------------------------------

class TestPrismDisclaimer:

    def test_disclaimer_available(self, engine):
        disclaimer = engine.get_prism_disclaimer()
        assert "PRISM" in disclaimer
        assert "employment" in disclaimer.lower()


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------

class TestDefaultRules:

    def test_hiring_human_review_for_nova(self, engine):
        """Default rules should include hiring_human_review targeting Nova."""
        nova_rules = [
            r for r in engine._global_rules
            if r.agent_id == AgentId.NOVA and r.name == "hiring_human_review"
        ]
        assert len(nova_rules) == 1
        assert nova_rules[0].min_confidence == 0.95
        assert nova_rules[0].requires_prism_disclaimer is True
        assert nova_rules[0].requires_sentinel_review is True
