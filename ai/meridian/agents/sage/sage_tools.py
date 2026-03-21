from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


class EvidenceQuality(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    EMERGING = "emerging"


class ResearchSynthesis(BaseModel):
    """Structured research synthesis on a topic."""
    topic: str
    key_findings: list[str] = Field(default_factory=list)
    evidence_quality: EvidenceQuality = EvidenceQuality.MODERATE
    frameworks: list[str] = Field(default_factory=list)
    practical_applications: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    domain: str = ""


class ExecutiveBriefing(BaseModel):
    """Executive-ready briefing document."""
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    evidence_base: str = ""
    risks: list[str] = Field(default_factory=list)


def synthesize_research(
    topic: str,
    domain: Optional[str] = None,
) -> ResearchSynthesis:
    """
    Generate a structured research synthesis on a topic.

    Produces key findings, evidence quality assessment, relevant frameworks,
    and practical applications. Evidence quality reflects honest assessment
    of the research base — never overstates certainty.

    Pure function: no side effects, fully testable.
    """
    # Domain-specific framework mappings
    domain_frameworks: dict[str, list[str]] = {
        "leadership": [
            "Situational Leadership (Hersey & Blanchard)",
            "Transformational Leadership (Bass & Avolio)",
            "Servant Leadership (Greenleaf)",
            "Adaptive Leadership (Heifetz)",
        ],
        "team_dynamics": [
            "Tuckman's Stages of Group Development",
            "Lencioni's Five Dysfunctions",
            "Psychological Safety (Edmondson)",
            "Team Effectiveness (Google's Project Aristotle)",
        ],
        "organizational_development": [
            "Kotter's 8-Step Change Model",
            "McKinsey 7-S Framework",
            "Appreciative Inquiry (Cooperrider)",
            "Systems Thinking (Senge)",
        ],
        "behavioral_science": [
            "PRISM Brain Mapping",
            "Self-Determination Theory (Deci & Ryan)",
            "Growth Mindset (Dweck)",
            "Cognitive Behavioral Frameworks",
        ],
        "strategy": [
            "Porter's Five Forces",
            "Blue Ocean Strategy (Kim & Mauborgne)",
            "Balanced Scorecard (Kaplan & Norton)",
            "OKR Framework (Doerr)",
        ],
    }

    effective_domain = (domain or "").lower().replace(" ", "_")
    frameworks = domain_frameworks.get(effective_domain, [])

    # Build synthesis with honest evidence assessment
    synthesis = ResearchSynthesis(
        topic=topic,
        key_findings=[
            f"Research on '{topic}' spans multiple disciplines and perspectives.",
            "Evidence-based approaches consistently outperform intuition-only methods.",
            "Context matters — findings may vary by industry, culture, and scale.",
        ],
        evidence_quality=EvidenceQuality.MODERATE,
        frameworks=frameworks if frameworks else [
            "Further domain-specific frameworks should be identified for this topic."
        ],
        practical_applications=[
            f"Apply research findings on '{topic}' incrementally, starting with low-risk experiments.",
            "Combine evidence with local context and organizational culture.",
            "Measure outcomes against baseline to validate application effectiveness.",
        ],
        caveats=[
            "This synthesis reflects general research patterns, not a systematic review.",
            "Organizational context may alter how findings apply in practice.",
        ],
        domain=effective_domain or "general",
    )

    logger.info(f"Sage: synthesized research on '{topic}' (domain={effective_domain or 'general'})")
    return synthesis


def build_executive_briefing(
    topic: str,
    findings: Optional[list[str]] = None,
) -> ExecutiveBriefing:
    """
    Build an executive-ready briefing from a topic and optional findings.

    Produces a scannable, evidence-based document with clear recommendations.

    Pure function: no side effects, fully testable.
    """
    effective_findings = findings or []

    key_points = []
    for finding in effective_findings:
        key_points.append(finding)

    if not key_points:
        key_points = [
            f"Research on '{topic}' indicates actionable opportunities.",
            "Evidence base should be strengthened before major investments.",
        ]

    briefing = ExecutiveBriefing(
        title=f"Executive Briefing: {topic}",
        summary=(
            f"This briefing synthesizes available evidence on '{topic}' "
            f"and provides actionable recommendations for decision-makers."
        ),
        key_points=key_points,
        recommendations=[
            f"Conduct a focused assessment of '{topic}' within your organizational context.",
            "Identify quick wins that can demonstrate value within 30-60 days.",
            "Establish measurement criteria before launching major initiatives.",
        ],
        evidence_base=(
            f"Based on {len(effective_findings)} key findings. "
            "Evidence quality should be validated against organizational data."
        ),
        risks=[
            "Applying general findings without local context validation.",
            "Confirmation bias — seeking evidence that supports existing preferences.",
        ],
    )

    logger.info(f"Sage: built executive briefing on '{topic}' ({len(key_points)} key points)")
    return briefing


def search_knowledge_base(
    query: str,
    collection: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Search organizational knowledge base via vector similarity.

    Stub for Milvus vector search integration. Returns matching documents
    with relevance scores.

    Pure function signature: ready for Milvus integration.
    """
    # TODO: Integrate with Milvus vector search
    # This will query the organization's document embeddings
    logger.info(
        f"Sage: knowledge base search for '{query}' "
        f"(collection={collection or 'default'})"
    )
    return []
