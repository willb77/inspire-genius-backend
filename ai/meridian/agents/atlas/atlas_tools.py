from __future__ import annotations

import math
from typing import Any, Optional
from pydantic import BaseModel, Field


class MemberProfile(BaseModel):
    """A team member with PRISM dimension scores."""
    user_id: str
    name: str = ""
    gold: int = Field(ge=0, le=100)
    green: int = Field(ge=0, le=100)
    blue: int = Field(ge=0, le=100)
    red: int = Field(ge=0, le=100)


class TeamComposition(BaseModel):
    """Analyzed team composition with PRISM diversity metrics."""
    team_id: str
    members: list[MemberProfile]
    dimension_averages: dict[str, float] = Field(default_factory=dict)
    diversity_score: float = 0.0
    gaps: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    recommended_hires: list[str] = Field(default_factory=list)


class TalentOptimizerScore(BaseModel):
    """Team behavioral diversity metrics."""
    team_id: str
    diversity_score: float = Field(ge=0.0, le=100.0)
    dimension_spread: dict[str, float] = Field(default_factory=dict)
    balance_rating: str = ""  # "well-balanced" | "moderate" | "skewed"
    complementarity_pairs: list[str] = Field(default_factory=list)


class WorkforcePlan(BaseModel):
    """Workforce planning output with gap analysis."""
    team_id: str
    current_headcount: int = 0
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    hiring_recommendations: list[dict[str, str]] = Field(default_factory=list)
    internal_mobility: list[dict[str, str]] = Field(default_factory=list)
    priority_order: list[str] = Field(default_factory=list)


def analyze_team_composition(
    team_id: str, members: list[dict[str, Any]]
) -> TeamComposition:
    """
    Analyze a team's PRISM behavioral composition.

    Computes diversity score as the standard deviation of dimension averages.
    Higher spread = more behaviorally diverse team.
    """
    profiles = [MemberProfile(**m) for m in members]

    if not profiles:
        return TeamComposition(team_id=team_id, members=[])

    # Compute dimension averages across the team
    dims = ["gold", "green", "blue", "red"]
    averages = {}
    for dim in dims:
        scores = [getattr(p, dim) for p in profiles]
        averages[dim] = round(sum(scores) / len(scores), 1)

    # Diversity score: std dev of averages (higher = more spread = more diverse)
    avg_values = list(averages.values())
    mean_avg = sum(avg_values) / len(avg_values)
    variance = sum((v - mean_avg) ** 2 for v in avg_values) / len(avg_values)
    diversity_score = round(math.sqrt(variance), 2)

    # Identify gaps (dimensions with average below 40)
    gaps = []
    for dim in dims:
        if averages[dim] < 40:
            gaps.append(
                f"{dim.title()} dimension is underrepresented "
                f"(team average: {averages[dim]})"
            )

    # Identify strengths (dimensions with average above 65)
    strengths = []
    for dim in dims:
        if averages[dim] >= 65:
            strengths.append(
                f"Strong {dim.title()} presence (team average: {averages[dim]})"
            )

    # Recommend hires to fill gaps
    recommended_hires = []
    for dim in dims:
        if averages[dim] < 40:
            recommended_hires.append(
                f"Consider candidates with strong {dim.title()} preference "
                f"to balance team composition"
            )

    return TeamComposition(
        team_id=team_id,
        members=profiles,
        dimension_averages=averages,
        diversity_score=diversity_score,
        gaps=gaps,
        strengths=strengths,
        recommended_hires=recommended_hires,
    )


def compute_talent_optimizer(team: TeamComposition) -> TalentOptimizerScore:
    """
    Score a team's behavioral diversity and identify complementary pairs.
    """
    dims = ["gold", "green", "blue", "red"]

    # Per-dimension spread: std dev of member scores within each dimension
    dimension_spread = {}
    for dim in dims:
        scores = [getattr(m, dim) for m in team.members]
        if len(scores) < 2:
            dimension_spread[dim] = 0.0
            continue
        mean = sum(scores) / len(scores)
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        dimension_spread[dim] = round(math.sqrt(var), 2)

    # Balance rating based on diversity score
    ds = team.diversity_score
    if ds < 8:
        balance_rating = "well-balanced"
    elif ds < 18:
        balance_rating = "moderate"
    else:
        balance_rating = "skewed"

    # Identify complementary pairs (members with opposite dominant dimensions)
    pairs = []
    for i, m1 in enumerate(team.members):
        for m2 in team.members[i + 1:]:
            m1_primary = max(dims, key=lambda d: getattr(m1, d))
            m2_primary = max(dims, key=lambda d: getattr(m2, d))
            if m1_primary != m2_primary:
                pairs.append(
                    f"{m1.name or m1.user_id} ({m1_primary.title()}) + "
                    f"{m2.name or m2.user_id} ({m2_primary.title()})"
                )

    return TalentOptimizerScore(
        team_id=team.team_id,
        diversity_score=min(team.diversity_score * 4, 100.0),
        dimension_spread=dimension_spread,
        balance_rating=balance_rating,
        complementarity_pairs=pairs[:10],  # cap at 10
    )


def build_workforce_plan(
    team: TeamComposition, target_roles: Optional[list[dict[str, Any]]] = None
) -> WorkforcePlan:
    """
    Build a workforce plan from current team composition and target roles.
    """
    dims = ["gold", "green", "blue", "red"]
    gaps = []
    hiring_recs = []
    priority_order = []

    # Gap analysis: dimensions below 40 average
    for dim in dims:
        avg = team.dimension_averages.get(dim, 50)
        if avg < 40:
            deficit = 50 - avg
            gaps.append({
                "dimension": dim,
                "current_average": avg,
                "target_average": 50.0,
                "deficit": round(deficit, 1),
            })
            hiring_recs.append({
                "role_focus": f"{dim.title()}-leaning behavioral profile",
                "rationale": (
                    f"Team {dim.title()} average is {avg}, below the "
                    f"balanced threshold of 50"
                ),
            })
            priority_order.append(dim)

    # Internal mobility suggestions
    internal_mobility = []
    for m in team.members:
        member_scores = {d: getattr(m, d) for d in dims}
        strongest = max(member_scores, key=member_scores.get)  # type: ignore[arg-type]
        if strongest in priority_order:
            continue  # already strong in a gap area — no move needed
        for gap_dim in priority_order:
            if member_scores[gap_dim] >= 55:
                internal_mobility.append({
                    "member": m.name or m.user_id,
                    "suggestion": (
                        f"Has latent {gap_dim.title()} strength "
                        f"(score: {member_scores[gap_dim]}) — could flex "
                        f"into {gap_dim.title()}-oriented responsibilities"
                    ),
                })

    return WorkforcePlan(
        team_id=team.team_id,
        current_headcount=len(team.members),
        gaps=gaps,
        hiring_recommendations=hiring_recs,
        internal_mobility=internal_mobility,
        priority_order=priority_order,
    )
