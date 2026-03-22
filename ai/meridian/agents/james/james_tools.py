from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import uuid


class JobBlueprint(BaseModel):
    """A Job Blueprint defining role requirements with behavioral fit criteria."""
    blueprint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    department: str = ""
    description: str = ""
    required_dimensions: dict[str, int] = Field(
        default_factory=dict,
        description="Target PRISM dimension scores for ideal fit (gold, green, blue, red)"
    )
    dimension_weights: dict[str, float] = Field(
        default_factory=lambda: {"gold": 0.25, "green": 0.25, "blue": 0.25, "red": 0.25},
        description="How much each dimension matters for this role"
    )
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_range: tuple[int, int] = (0, 99)
    competencies: list[str] = Field(default_factory=list)


class FitDimensionScore(BaseModel):
    """Fit score for a single PRISM dimension."""
    dimension: str
    candidate_score: int
    blueprint_target: int
    gap: int
    weight: float
    weighted_score: float
    assessment: str  # "strong", "moderate", "development_needed"


class CandidateFitReport(BaseModel):
    """Complete fit analysis for a candidate against a Job Blueprint."""
    candidate_id: str
    blueprint_id: str
    overall_fit_score: float = Field(ge=0.0, le=1.0)
    behavioral_fit: float = Field(ge=0.0, le=1.0)
    skill_fit: float = Field(ge=0.0, le=1.0)
    growth_potential: float = Field(ge=0.0, le=1.0)
    dimension_scores: list[FitDimensionScore] = Field(default_factory=list)
    tier: str = "pending_assessment"
    strengths: list[str] = Field(default_factory=list)
    development_areas: list[str] = Field(default_factory=list)
    interview_focus_areas: list[str] = Field(default_factory=list)
    narrative: str = ""


class InterviewGuide(BaseModel):
    """Behavioral interview guide for a specific candidate-role pair."""
    candidate_id: str
    blueprint_id: str
    questions: list[dict[str, str]] = Field(default_factory=list)
    focus_dimensions: list[str] = Field(default_factory=list)
    red_flags_to_probe: list[str] = Field(default_factory=list)


def score_behavioral_fit(
    candidate_dimensions: dict[str, int],
    blueprint: JobBlueprint,
) -> tuple[float, list[FitDimensionScore]]:
    """
    Score a candidate's PRISM dimensions against a Job Blueprint.

    Returns overall behavioral fit score (0-1) and per-dimension analysis.
    """
    dimension_scores = []
    total_weighted = 0.0
    total_weight = 0.0

    for dim in ["gold", "green", "blue", "red"]:
        candidate_score = candidate_dimensions.get(dim, 50)
        target = blueprint.required_dimensions.get(dim, 50)
        weight = blueprint.dimension_weights.get(dim, 0.25)
        gap = abs(candidate_score - target)

        # Score: 1.0 for perfect match, decreasing with gap
        # Gap of 0 = 1.0, gap of 50 = 0.0
        raw_score = max(0.0, 1.0 - (gap / 50.0))
        weighted = raw_score * weight

        if gap <= 10:
            assessment = "strong"
        elif gap <= 25:
            assessment = "moderate"
        else:
            assessment = "development_needed"

        dimension_scores.append(FitDimensionScore(
            dimension=dim,
            candidate_score=candidate_score,
            blueprint_target=target,
            gap=gap,
            weight=weight,
            weighted_score=weighted,
            assessment=assessment,
        ))

        total_weighted += weighted
        total_weight += weight

    overall = total_weighted / total_weight if total_weight > 0 else 0.0
    return overall, dimension_scores


def score_skill_fit(
    candidate_skills: list[str],
    blueprint: JobBlueprint,
) -> float:
    """Score how well candidate skills match the blueprint."""
    if not blueprint.required_skills:
        return 0.75  # No specific requirements = moderate default

    required = set(s.lower() for s in blueprint.required_skills)
    candidate = set(s.lower() for s in candidate_skills)

    matched = required & candidate
    score = len(matched) / len(required) if required else 0.5

    # Bonus for preferred skills
    preferred = set(s.lower() for s in blueprint.preferred_skills)
    preferred_matched = preferred & candidate
    if preferred:
        bonus = 0.1 * (len(preferred_matched) / len(preferred))
        score = min(1.0, score + bonus)

    return score


def assess_growth_potential(
    behavioral_fit: float,
    skill_fit: float,
    dimension_scores: list[FitDimensionScore],
) -> float:
    """Assess growth potential based on fit gaps and patterns."""
    development_dims = [d for d in dimension_scores if d.assessment == "development_needed"]
    moderate_dims = [d for d in dimension_scores if d.assessment == "moderate"]

    # High growth potential: moderate gaps (not extreme) + decent skill base
    if not development_dims and skill_fit >= 0.5:
        return 0.90  # Already a strong fit with skills
    elif len(development_dims) <= 1 and skill_fit >= 0.4:
        return 0.75  # One area to develop, coachable
    elif len(development_dims) <= 2 and skill_fit >= 0.3:
        return 0.55  # Some development needed
    else:
        return 0.35  # Significant development needed


def classify_candidate(
    overall_score: float,
    behavioral_fit: float,
) -> str:
    """Classify candidate into triage tier."""
    if overall_score >= 0.75 and behavioral_fit >= 0.70:
        return "strong_fit"
    elif overall_score >= 0.55 and behavioral_fit >= 0.50:
        return "potential_fit"
    else:
        return "misalignment_detected"


def generate_fit_report(
    candidate_id: str,
    candidate_dimensions: dict[str, int],
    candidate_skills: list[str],
    blueprint: JobBlueprint,
) -> CandidateFitReport:
    """Generate a complete fit report for a candidate."""
    behavioral_fit, dim_scores = score_behavioral_fit(candidate_dimensions, blueprint)
    skill_fit = score_skill_fit(candidate_skills, blueprint)
    growth = assess_growth_potential(behavioral_fit, skill_fit, dim_scores)

    # Weighted overall: behavioral 40%, skill 35%, growth 25%
    overall = (behavioral_fit * 0.40) + (skill_fit * 0.35) + (growth * 0.25)
    tier = classify_candidate(overall, behavioral_fit)

    strengths = [
        f"Strong {d.dimension.title()} alignment ({d.candidate_score} vs target {d.blueprint_target})"
        for d in dim_scores if d.assessment == "strong"
    ]
    development = [
        f"{d.dimension.title()} development needed ({d.candidate_score} vs target {d.blueprint_target})"
        for d in dim_scores if d.assessment == "development_needed"
    ]
    interview_focus = [
        f"Explore {d.dimension.title()} behaviors in work scenarios"
        for d in dim_scores if d.assessment in ("moderate", "development_needed")
    ]

    tier_label = {
        "strong_fit": "Strong Fit",
        "potential_fit": "Potential Fit (Development Required)",
        "misalignment_detected": "Misalignment Detected",
    }

    narrative = (
        f"Classification: {tier_label.get(tier, tier)}. "
        f"Overall fit score: {overall:.0%} "
        f"(behavioral: {behavioral_fit:.0%}, skill: {skill_fit:.0%}, "
        f"growth potential: {growth:.0%}). "
    )
    if strengths:
        narrative += f"Strengths: {'; '.join(strengths)}. "
    if development:
        narrative += f"Development areas: {'; '.join(development)}."

    return CandidateFitReport(
        candidate_id=candidate_id,
        blueprint_id=blueprint.blueprint_id,
        overall_fit_score=overall,
        behavioral_fit=behavioral_fit,
        skill_fit=skill_fit,
        growth_potential=growth,
        dimension_scores=dim_scores,
        tier=tier,
        strengths=strengths,
        development_areas=development,
        interview_focus_areas=interview_focus,
        narrative=narrative,
    )


def generate_interview_questions(
    fit_report: CandidateFitReport,
    blueprint: JobBlueprint,
) -> InterviewGuide:
    """Generate behavioral interview questions based on fit analysis."""
    questions = []
    focus_dims = []
    red_flags = []

    for dim_score in fit_report.dimension_scores:
        dim = dim_score.dimension
        if dim_score.assessment in ("moderate", "development_needed"):
            focus_dims.append(dim)

            q_map = {
                "gold": {
                    "question": "Tell me about a time you had to organize a complex project with many moving parts. How did you approach it?",
                    "follow_up": "What happens when your structured plan meets unexpected changes?",
                    "probes": "organization, attention to detail, adaptability",
                },
                "green": {
                    "question": "Describe a situation where you had to navigate a disagreement between team members. What was your approach?",
                    "follow_up": "How do you balance empathy for individuals with team objectives?",
                    "probes": "empathy, conflict resolution, team dynamics",
                },
                "blue": {
                    "question": "Walk me through how you've used data to make an important decision. What was the process?",
                    "follow_up": "How do you handle situations where the data is incomplete or contradictory?",
                    "probes": "analytical thinking, evidence-based decisions, ambiguity tolerance",
                },
                "red": {
                    "question": "Tell me about a time you had to make a quick decision with limited information. What did you do?",
                    "follow_up": "How do you ensure speed doesn't come at the expense of quality?",
                    "probes": "decisiveness, action orientation, risk management",
                },
            }
            if dim in q_map:
                questions.append(q_map[dim])

        if dim_score.assessment == "development_needed":
            red_flags.append(
                f"Significant gap in {dim} ({dim_score.candidate_score} vs "
                f"target {dim_score.blueprint_target}) — probe with behavioral examples"
            )

    # Always add a general behavioral question
    questions.append({
        "question": "What work environment brings out your best performance?",
        "follow_up": "How do you adapt when the environment doesn't match your preference?",
        "probes": "self-awareness, adaptability, preference flexibility",
    })

    return InterviewGuide(
        candidate_id=fit_report.candidate_id,
        blueprint_id=fit_report.blueprint_id,
        questions=questions,
        focus_dimensions=focus_dims,
        red_flags_to_probe=red_flags,
    )
