from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from prism_inspire.core.log_config import logger
import uuid


class CandidateTier(str, Enum):
    STRONG_FIT = "strong_fit"
    POTENTIAL_FIT = "potential_fit"
    MISALIGNMENT = "misalignment_detected"
    PENDING = "pending_assessment"


class CandidateSubmission(BaseModel):
    """A candidate submitted for evaluation."""
    candidate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[str] = None
    job_blueprint_id: str
    resume_summary: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    experience_years: Optional[int] = None
    prism_assessment_id: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class CareerPathway(BaseModel):
    """A career pathway recommendation."""
    title: str
    description: str
    milestones: list[dict[str, Any]] = Field(default_factory=list)
    behavioral_alignment: str = ""
    estimated_timeline: str = ""
    skills_to_develop: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    """Result of the Nova-James triage for a single candidate."""
    candidate_id: str
    job_blueprint_id: str
    tier: CandidateTier
    fit_score: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    development_areas: list[str] = Field(default_factory=list)
    recommendation: str = ""
    prism_disclaimer: str = (
        "PRISM behavioral data provides insights into behavioral preferences. "
        "This data should not be used as the sole basis for hiring decisions. "
        "All decisions must consider qualifications, experience, and performance."
    )


class HiringDashboardEntry(BaseModel):
    """Entry for the hiring dashboard."""
    job_blueprint_id: str
    job_title: str
    candidates: list[TriageResult] = Field(default_factory=list)
    total_candidates: int = 0
    strong_fit_count: int = 0
    potential_fit_count: int = 0
    misalignment_count: int = 0
    pending_count: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


def build_career_pathways(
    behavioral_context: Optional[dict[str, Any]],
    current_role: Optional[str] = None,
    goals: Optional[list[str]] = None,
) -> list[CareerPathway]:
    """Build career pathway recommendations based on behavioral profile and goals."""
    pathways = []
    if not behavioral_context:
        pathways.append(CareerPathway(
            title="Career Exploration",
            description="Complete a PRISM assessment to get personalized career pathway recommendations.",
            estimated_timeline="Start now",
        ))
        return pathways

    primary = behavioral_context.get("primary_preference", "")
    secondary = behavioral_context.get("secondary_preference", "")

    pathway_map = {
        "gold": [
            CareerPathway(
                title="Operations & Process Leadership",
                description="Your structured approach makes you well-suited for roles that require systematic thinking and attention to detail.",
                behavioral_alignment="Strong Gold preference aligns with organizational and quality-focused roles",
                skills_to_develop=["Strategic delegation", "Adaptability in ambiguous situations"],
            ),
            CareerPathway(
                title="Project & Program Management",
                description="Your natural ability to organize and track details is a strong fit for managing complex initiatives.",
                behavioral_alignment="Gold structure + detail orientation drive project success",
                skills_to_develop=["Stakeholder influence", "Risk tolerance"],
            ),
        ],
        "green": [
            CareerPathway(
                title="People & Culture Leadership",
                description="Your empathy and people-focus position you well for roles centered on team development.",
                behavioral_alignment="Strong Green preference aligns with people-centric leadership",
                skills_to_develop=["Difficult conversations", "Data-driven decision making"],
            ),
            CareerPathway(
                title="Client Success & Relationship Management",
                description="Your natural ability to connect and empathize drives strong client relationships.",
                behavioral_alignment="Green empathy builds lasting client partnerships",
                skills_to_develop=["Negotiation", "Revenue focus"],
            ),
        ],
        "blue": [
            CareerPathway(
                title="Analytics & Strategy",
                description="Your analytical mindset positions you for roles requiring data-driven strategy.",
                behavioral_alignment="Strong Blue preference aligns with analytical and strategic roles",
                skills_to_develop=["Storytelling with data", "Collaborative decision-making"],
            ),
            CareerPathway(
                title="Technical Leadership",
                description="Your analytical depth combined with systematic thinking drives technical excellence.",
                behavioral_alignment="Blue analysis enables sound technical direction",
                skills_to_develop=["People management", "Executive communication"],
            ),
        ],
        "red": [
            CareerPathway(
                title="Entrepreneurial & Growth Leadership",
                description="Your action orientation and drive make you well-suited for growth-focused roles.",
                behavioral_alignment="Strong Red preference aligns with execution and results-driven roles",
                skills_to_develop=["Patience with process", "Inclusive decision-making"],
            ),
            CareerPathway(
                title="Sales & Business Development",
                description="Your decisive nature and results-focus are natural fits for revenue generation.",
                behavioral_alignment="Red drive powers competitive environments",
                skills_to_develop=["Long-term relationship building", "Active listening"],
            ),
        ],
    }

    pathways = pathway_map.get(primary, [])
    if not pathways:
        pathways = [CareerPathway(
            title="Personalized Career Strategy",
            description="Let's explore career options that align with your unique behavioral profile.",
            behavioral_alignment=f"Based on your {primary}-{secondary} combination",
        )]

    return pathways


def aggregate_triage_dashboard(
    job_blueprint_id: str,
    job_title: str,
    triage_results: list[TriageResult],
) -> HiringDashboardEntry:
    """Aggregate triage results into a dashboard entry."""
    entry = HiringDashboardEntry(
        job_blueprint_id=job_blueprint_id,
        job_title=job_title,
        candidates=triage_results,
        total_candidates=len(triage_results),
        strong_fit_count=sum(1 for r in triage_results if r.tier == CandidateTier.STRONG_FIT),
        potential_fit_count=sum(1 for r in triage_results if r.tier == CandidateTier.POTENTIAL_FIT),
        misalignment_count=sum(1 for r in triage_results if r.tier == CandidateTier.MISALIGNMENT),
        pending_count=sum(1 for r in triage_results if r.tier == CandidateTier.PENDING),
    )
    return entry
