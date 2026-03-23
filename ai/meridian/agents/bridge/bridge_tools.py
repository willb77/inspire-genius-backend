from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PipelineHealth(BaseModel):
    """Health metrics for a school's talent pipeline."""
    pipeline_id: str
    school_id: str
    active_students: int = 0
    placement_rate: float = 0.0  # 0.0 - 1.0
    avg_time_to_placement: float = 0.0  # days
    status: str = "healthy"  # healthy | at_risk | critical
    recommendations: list[str] = Field(default_factory=list)


class EmployerMatch(BaseModel):
    """A single employer match for a student."""
    employer_id: str
    employer_name: str = ""
    fit_score: float = Field(ge=0.0, le=1.0, default=0.0)
    skill_overlap: float = Field(ge=0.0, le=1.0, default=0.0)
    prism_alignment: float = Field(ge=0.0, le=1.0, default=0.0)
    rationale: str = ""


class StudentMatch(BaseModel):
    """Student-to-employer matching result."""
    student_id: str
    employer_matches: list[EmployerMatch] = Field(default_factory=list)
    placement_status: str = "unmatched"  # unmatched | matched | placed


class EmployerPipeline(BaseModel):
    """Employer-side pipeline view."""
    employer_id: str
    pipeline_id: str
    candidate_count: int = 0
    forecast: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def assess_pipeline_health(pipeline_data: dict[str, Any]) -> PipelineHealth:
    """
    Assess the health of a talent pipeline from school perspective.

    Evaluates placement rate, time-to-placement, and active student count
    to determine pipeline status and generate recommendations.
    """
    pipeline_id = pipeline_data.get("pipeline_id", "unknown")
    school_id = pipeline_data.get("school_id", "unknown")
    active_students = pipeline_data.get("active_students", 0)
    placed = pipeline_data.get("placed_students", 0)
    total = pipeline_data.get("total_students", max(active_students, 1))
    avg_days = pipeline_data.get("avg_time_to_placement_days", 0.0)

    placement_rate = placed / total if total > 0 else 0.0

    # Determine status
    recommendations = []
    if placement_rate >= 0.7 and avg_days <= 90:
        status = "healthy"
    elif placement_rate >= 0.4 or avg_days <= 180:
        status = "at_risk"
        if placement_rate < 0.7:
            recommendations.append(
                f"Placement rate ({placement_rate:.0%}) is below target (70%). "
                "Consider expanding employer partnerships."
            )
        if avg_days > 90:
            recommendations.append(
                f"Average time to placement ({avg_days:.0f} days) is elevated. "
                "Review matching criteria and student readiness."
            )
    else:
        status = "critical"
        recommendations.append(
            "Pipeline requires immediate attention. Both placement rate and "
            "time-to-placement are outside acceptable ranges."
        )

    if active_students < 10:
        recommendations.append(
            "Low active student count. Focus on student engagement and "
            "program enrollment."
        )

    return PipelineHealth(
        pipeline_id=pipeline_id,
        school_id=school_id,
        active_students=active_students,
        placement_rate=round(placement_rate, 3),
        avg_time_to_placement=avg_days,
        status=status,
        recommendations=recommendations,
    )


def match_student_to_employers(
    student_profile: dict[str, Any],
    employers: list[dict[str, Any]],
) -> StudentMatch:
    """
    Match a student to employers using skill overlap and PRISM alignment.

    Scoring:
    - 60% weight: skill overlap (Jaccard similarity)
    - 40% weight: PRISM alignment (inverse of dimension distance)
    """
    student_id = student_profile.get("student_id", "unknown")
    student_skills = set(student_profile.get("skills", []))
    student_prism = student_profile.get("prism", {})

    matches = []
    for emp in employers:
        emp_id = emp.get("employer_id", "unknown")
        emp_name = emp.get("name", "")
        required_skills = set(emp.get("required_skills", []))
        emp_prism = emp.get("preferred_prism", {})

        # Skill overlap (Jaccard)
        if student_skills or required_skills:
            intersection = student_skills & required_skills
            union = student_skills | required_skills
            skill_overlap = len(intersection) / len(union) if union else 0.0
        else:
            skill_overlap = 0.5  # neutral when no data

        # PRISM alignment (normalised inverse distance)
        prism_alignment = _compute_prism_alignment(student_prism, emp_prism)

        fit_score = round(0.6 * skill_overlap + 0.4 * prism_alignment, 3)

        rationale_parts = []
        if skill_overlap >= 0.6:
            rationale_parts.append("strong skill match")
        elif skill_overlap >= 0.3:
            rationale_parts.append("moderate skill overlap")
        else:
            rationale_parts.append("limited skill overlap — growth opportunity")

        if prism_alignment >= 0.7:
            rationale_parts.append("excellent behavioral alignment")
        elif prism_alignment >= 0.4:
            rationale_parts.append("reasonable behavioral fit")

        matches.append(EmployerMatch(
            employer_id=emp_id,
            employer_name=emp_name,
            fit_score=fit_score,
            skill_overlap=round(skill_overlap, 3),
            prism_alignment=round(prism_alignment, 3),
            rationale="; ".join(rationale_parts),
        ))

    # Sort by fit score descending
    matches.sort(key=lambda m: m.fit_score, reverse=True)

    return StudentMatch(
        student_id=student_id,
        employer_matches=matches,
        placement_status="unmatched",
    )


def forecast_pipeline(pipeline: PipelineHealth) -> dict[str, Any]:
    """
    Basic pipeline forecast based on current metrics.

    Extrapolates placement rate and time trends for 30/60/90-day windows.
    """
    rate = pipeline.placement_rate
    active = pipeline.active_students
    avg_days = pipeline.avg_time_to_placement

    # Simple linear extrapolation
    monthly_placements = (rate * active) / max(avg_days / 30, 1) if avg_days > 0 else 0

    return {
        "pipeline_id": pipeline.pipeline_id,
        "current_placement_rate": rate,
        "projected_placements_30d": round(monthly_placements, 1),
        "projected_placements_60d": round(monthly_placements * 2, 1),
        "projected_placements_90d": round(monthly_placements * 3, 1),
        "risk_level": pipeline.status,
        "active_students_remaining": max(
            active - round(monthly_placements * 3), 0
        ),
    }


def _compute_prism_alignment(
    student_prism: dict[str, Any], employer_prism: dict[str, Any]
) -> float:
    """
    Compute PRISM alignment between student and employer preferences.

    Uses normalised inverse Euclidean distance across the four dimensions.
    Returns 0.0-1.0 (1.0 = perfect alignment).
    """
    dims = ["gold", "green", "blue", "red"]

    if not student_prism or not employer_prism:
        return 0.5  # neutral when no data

    total_sq = 0.0
    for dim in dims:
        s = student_prism.get(dim, 50)
        e = employer_prism.get(dim, 50)
        total_sq += (s - e) ** 2

    # Max possible distance: 4 * 100^2 = 40000
    max_distance = 200.0  # sqrt(40000)
    distance = total_sq ** 0.5
    alignment = 1.0 - (distance / max_distance)
    return round(max(alignment, 0.0), 3)
