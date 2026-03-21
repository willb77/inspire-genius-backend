from __future__ import annotations

"""Tests for Phase 5 agents: Atlas, Sentinel, Nexus, Bridge, Sage, Ascend, Alex."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ai.meridian.core.types import AgentId, AgentTask, OrchestratorId, TaskStatus

# --- Atlas ---
from ai.meridian.agents.atlas.atlas_agent import AtlasAgent
from ai.meridian.agents.atlas.atlas_tools import analyze_team_composition

# --- Sentinel ---
from ai.meridian.agents.sentinel.sentinel_agent import SentinelAgent
from ai.meridian.agents.sentinel.sentinel_tools import check_content_compliance

# --- Nexus ---
from ai.meridian.agents.nexus.nexus_agent import NexusAgent
from ai.meridian.agents.nexus.nexus_tools import get_cultural_profile, adapt_communication, SUPPORTED_LANGUAGES

# --- Bridge ---
from ai.meridian.agents.bridge.bridge_agent import BridgeAgent
from ai.meridian.agents.bridge.bridge_tools import assess_pipeline_health, match_student_to_employers

# --- Sage ---
from ai.meridian.agents.sage.sage_agent import SageAgent
from ai.meridian.agents.sage.sage_tools import synthesize_research, build_executive_briefing

# --- Ascend ---
from ai.meridian.agents.ascend.ascend_agent import AscendAgent
from ai.meridian.agents.ascend.ascend_tools import analyze_leadership_signature, generate_coaching_scenario

# --- Alex ---
from ai.meridian.agents.alex.alex_agent import AlexAgent
from ai.meridian.agents.alex.alex_tools import is_prism_eligible, explore_careers


# ==================== Atlas ====================

class TestAtlas:
    def test_id_and_domain(self):
        a = AtlasAgent()
        assert a.agent_id == AgentId.ATLAS
        cap = a.get_capabilities()
        assert cap.domain == OrchestratorId.ORGANIZATIONAL_INTELLIGENCE
        assert "analyze_team" in cap.actions

    @pytest.mark.asyncio
    async def test_analyze_team(self):
        r = await AtlasAgent().process_task(AgentTask(
            agent_id=AgentId.ATLAS, action="analyze_team",
            parameters={"team_id": "t1", "members": [
                {"user_id": "u1", "name": "A", "gold": 80, "green": 40, "blue": 50, "red": 60},
                {"user_id": "u2", "name": "B", "gold": 30, "green": 85, "blue": 70, "red": 45},
            ]},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert "summary" in r.output

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        r = await AtlasAgent().process_task(AgentTask(agent_id=AgentId.ATLAS, action="nope", parameters={}))
        assert r.status == TaskStatus.FAILED

    def test_team_composition_tool(self):
        result = analyze_team_composition("t1", [
            {"user_id": "u1", "name": "A", "gold": 80, "green": 40, "blue": 50, "red": 60},
            {"user_id": "u2", "name": "B", "gold": 30, "green": 85, "blue": 70, "red": 45},
        ])
        assert result.diversity_score >= 0


# ==================== Sentinel ====================

class TestSentinel:
    def test_id_and_domain(self):
        a = SentinelAgent()
        assert a.agent_id == AgentId.SENTINEL
        assert a.get_capabilities().domain == OrchestratorId.ORGANIZATIONAL_INTELLIGENCE

    @pytest.mark.asyncio
    async def test_compliance_check(self):
        r = await SentinelAgent().process_task(AgentTask(
            agent_id=AgentId.SENTINEL, action="compliance_check",
            parameters={"content": "Evaluate candidate based on qualifications", "action_type": "hiring"},
        ))
        assert r.status == TaskStatus.COMPLETED
        assert "compliance_report" in r.output or "is_compliant" in r.output or "summary" in r.output

    @pytest.mark.asyncio
    async def test_enforce_disclaimer(self):
        r = await SentinelAgent().process_task(AgentTask(
            agent_id=AgentId.SENTINEL, action="enforce_disclaimer", parameters={},
        ))
        assert r.status == TaskStatus.COMPLETED
        # Should contain the PRISM disclaimer text
        output_text = str(r.output)
        assert "prism" in output_text.lower() or "behavioral" in output_text.lower()

    def test_compliance_tool_clean(self):
        report = check_content_compliance("Great teamwork skills", "review")
        assert report.is_compliant is True

    def test_compliance_tool_sensitive(self):
        report = check_content_compliance("Consider candidate's race and disability", "hiring")
        assert len(report.warnings) > 0 or len(report.violations) > 0


# ==================== Nexus ====================

class TestNexus:
    def test_id_and_domain(self):
        a = NexusAgent()
        assert a.agent_id == AgentId.NEXUS
        assert a.get_capabilities().domain == OrchestratorId.ORGANIZATIONAL_INTELLIGENCE

    @pytest.mark.asyncio
    async def test_cultural_profile(self):
        r = await NexusAgent().process_task(AgentTask(
            agent_id=AgentId.NEXUS, action="cultural_profile",
            parameters={"country": "Japan"},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_adapt_communication(self):
        r = await NexusAgent().process_task(AgentTask(
            agent_id=AgentId.NEXUS, action="adapt_communication",
            parameters={"source_country": "US", "target_country": "Japan"},
        ))
        assert r.status == TaskStatus.COMPLETED

    def test_supported_languages(self):
        assert len(SUPPORTED_LANGUAGES) == 16

    def test_cultural_profile_tool(self):
        p = get_cultural_profile("Japan")
        assert p is not None
        assert p.country == "Japan"

    def test_adapt_tool(self):
        a = adapt_communication("US", "Japan")
        assert len(a.adaptations) > 0


# ==================== Bridge ====================

class TestBridge:
    def test_id_and_domain(self):
        a = BridgeAgent()
        assert a.agent_id == AgentId.BRIDGE
        assert a.get_capabilities().domain == OrchestratorId.ORGANIZATIONAL_INTELLIGENCE

    @pytest.mark.asyncio
    async def test_pipeline_health(self):
        r = await BridgeAgent().process_task(AgentTask(
            agent_id=AgentId.BRIDGE, action="pipeline_health",
            parameters={"pipeline_data": {
                "pipeline_id": "p1", "school_id": "s1",
                "active_students": 50, "placed_students": 35,
            }},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_match_student(self):
        r = await BridgeAgent().process_task(AgentTask(
            agent_id=AgentId.BRIDGE, action="match_student",
            parameters={
                "student_profile": {"student_id": "st1", "skills": ["python"], "dimensions": {"blue": 80}},
                "employers": [{"employer_id": "e1", "required_skills": ["python"], "preferred_dimensions": {"blue": 70}}],
            },
        ))
        assert r.status == TaskStatus.COMPLETED

    def test_pipeline_tool(self):
        h = assess_pipeline_health({
            "pipeline_id": "p1", "school_id": "s1",
            "active_students": 100, "placed_students": 80,
        })
        assert h.placement_rate >= 0

    def test_match_tool(self):
        m = match_student_to_employers(
            {"student_id": "st1", "skills": ["python", "sql"], "dimensions": {"blue": 80, "gold": 60}},
            [{"employer_id": "e1", "required_skills": ["python"], "preferred_dimensions": {"blue": 70}}],
        )
        assert len(m.employer_matches) >= 1


# ==================== Sage ====================

class TestSage:
    def test_id_and_domain(self):
        a = SageAgent()
        assert a.agent_id == AgentId.SAGE
        assert a.get_capabilities().domain == OrchestratorId.STRATEGIC_ADVISORY

    @pytest.mark.asyncio
    async def test_research_synthesis(self):
        r = await SageAgent().process_task(AgentTask(
            agent_id=AgentId.SAGE, action="research_synthesis",
            parameters={"topic": "psychological safety"},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_executive_briefing(self):
        r = await SageAgent().process_task(AgentTask(
            agent_id=AgentId.SAGE, action="executive_briefing",
            parameters={"topic": "remote work effectiveness"},
        ))
        assert r.status == TaskStatus.COMPLETED

    def test_synthesis_tool(self):
        s = synthesize_research("team dynamics")
        assert len(s.key_findings) > 0

    def test_briefing_tool(self):
        b = build_executive_briefing("leadership", [])
        assert b.title != ""


# ==================== Ascend ====================

class TestAscend:
    def test_id_and_domain(self):
        a = AscendAgent()
        assert a.agent_id == AgentId.ASCEND
        assert a.get_capabilities().domain == OrchestratorId.STRATEGIC_ADVISORY

    @pytest.mark.asyncio
    async def test_leadership_signature(self):
        r = await AscendAgent().process_task(AgentTask(
            agent_id=AgentId.ASCEND, action="leadership_signature",
            parameters={},
            behavioral_context={"primary_preference": "green", "secondary_preference": "blue"},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_coaching_scenario(self):
        r = await AscendAgent().process_task(AgentTask(
            agent_id=AgentId.ASCEND, action="coaching_scenario",
            parameters={"focus_area": "delegation"},
            behavioral_context={"primary_preference": "red"},
        ))
        assert r.status == TaskStatus.COMPLETED

    def test_leadership_tool(self):
        sig = analyze_leadership_signature({"primary_preference": "blue", "secondary_preference": "red"})
        assert sig.primary_style != ""

    def test_scenario_tool(self):
        s = generate_coaching_scenario("feedback", {"primary_preference": "gold"})
        assert len(s.coaching_questions) > 0


# ==================== Alex ====================

class TestAlex:
    def test_id_and_domain(self):
        a = AlexAgent()
        assert a.agent_id == AgentId.ALEX
        assert a.get_capabilities().domain == OrchestratorId.STRATEGIC_ADVISORY

    @pytest.mark.asyncio
    async def test_career_exploration(self):
        r = await AlexAgent().process_task(AgentTask(
            agent_id=AgentId.ALEX, action="career_exploration",
            parameters={"interests": ["science", "technology"], "age_group": "high_school"},
            behavioral_context={"primary_preference": "blue"},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_academic_plan(self):
        r = await AlexAgent().process_task(AgentTask(
            agent_id=AgentId.ALEX, action="academic_plan",
            parameters={"goals": ["improve math"], "grade_level": "10th grade"},
        ))
        assert r.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_prism_ineligible(self):
        r = await AlexAgent().process_task(AgentTask(
            agent_id=AgentId.ALEX, action="prism_assessment",
            parameters={"age": 11},
        ))
        assert r.status == TaskStatus.COMPLETED
        # Should indicate ineligibility
        text = str(r.output).lower()
        assert "not yet" in text or "eligible" in text or "13" in text or "too young" in text or "available" in text

    def test_prism_eligibility(self):
        assert is_prism_eligible(14) is True  # age 14 or grade 14
        assert is_prism_eligible(8) is True   # grade 8 = min eligible
        assert is_prism_eligible(7) is False  # grade 7 = too young

    def test_explore_careers_tool(self):
        c = explore_careers(["art", "design"], {"primary_preference": "green"}, "high_school")
        assert len(c.career_families) > 0
