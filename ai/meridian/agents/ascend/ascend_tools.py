from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


# ------------------------------------------------------------------
# PRISM → Leadership style mapping
# ------------------------------------------------------------------

LEADERSHIP_STYLES: dict[str, dict[str, Any]] = {
    "gold": {
        "style": "Methodical Leader",
        "description": (
            "Systematic, reliable, detail-driven. You lead through structure, "
            "consistency, and thoroughness. Teams trust you because you follow through."
        ),
        "strengths": [
            "Creates clear processes and expectations",
            "Excels at planning and risk mitigation",
            "Builds reliable, high-quality operations",
        ],
        "blind_spots": [
            "May resist change or ambiguity",
            "Can over-plan at the expense of speed",
            "May undervalue creative or unconventional approaches",
        ],
    },
    "green": {
        "style": "Servant Leader",
        "description": (
            "Empathetic, team-first, relationship-driven. You lead by developing "
            "others and creating environments where people thrive."
        ),
        "strengths": [
            "Builds deep trust and psychological safety",
            "Excels at developing and mentoring talent",
            "Creates inclusive, collaborative team cultures",
        ],
        "blind_spots": [
            "May avoid difficult conversations or decisions",
            "Can prioritize harmony over accountability",
            "May absorb too much emotional labor from the team",
        ],
    },
    "blue": {
        "style": "Strategic Leader",
        "description": (
            "Analytical, vision-driven, systems-thinking. You lead through "
            "insight, strategy, and intellectual rigor."
        ),
        "strengths": [
            "Excels at long-term vision and strategic planning",
            "Makes well-reasoned, data-informed decisions",
            "Identifies patterns and opportunities others miss",
        ],
        "blind_spots": [
            "May over-analyze at the expense of action",
            "Can appear detached or overly cerebral to teams",
            "May undervalue emotional and relational dynamics",
        ],
    },
    "red": {
        "style": "Directive Leader",
        "description": (
            "Decisive, results-driven, pace-setting. You lead through energy, "
            "urgency, and an unwavering focus on outcomes."
        ),
        "strengths": [
            "Drives results and maintains momentum",
            "Makes fast decisions in ambiguous situations",
            "Creates energy and urgency in the organization",
        ],
        "blind_spots": [
            "May steamroll quieter voices on the team",
            "Can prioritize speed over thoroughness",
            "May burn out the team with relentless pace",
        ],
    },
}


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class LeadershipSignature(BaseModel):
    """A leader's behavioral leadership signature."""
    user_id: str
    primary_style: str
    secondary_style: str
    strengths: list[str] = Field(default_factory=list)
    blind_spots: list[str] = Field(default_factory=list)
    executive_presence_score: float = Field(ge=0.0, le=1.0, default=0.5)
    style_description: str = ""


class TeamCompatibility(BaseModel):
    """Assessment of leader-team behavioral compatibility."""
    leader_id: str
    team_members: list[str] = Field(default_factory=list)
    compatibility_score: float = Field(ge=0.0, le=1.0, default=0.5)
    friction_areas: list[str] = Field(default_factory=list)
    synergies: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CoachingScenario(BaseModel):
    """A leadership coaching scenario for development."""
    scenario: str
    challenge: str
    coaching_questions: list[str] = Field(default_factory=list)
    development_focus: str = ""


# ------------------------------------------------------------------
# Pure functions
# ------------------------------------------------------------------

def analyze_leadership_signature(
    behavioral_context: Optional[dict[str, Any]],
    user_id: str = "",
) -> LeadershipSignature:
    """
    Map PRISM behavioral preferences to a leadership signature.

    Gold = Methodical Leader, Green = Servant Leader,
    Blue = Strategic Leader, Red = Directive Leader.

    Pure function: no side effects, fully testable.
    """
    if not behavioral_context:
        return LeadershipSignature(
            user_id=user_id,
            primary_style="Unknown",
            secondary_style="Unknown",
            strengths=[],
            blind_spots=[],
            executive_presence_score=0.0,
            style_description=(
                "A PRISM behavioral assessment is needed to map your "
                "leadership signature."
            ),
        )

    primary = behavioral_context.get("primary_preference", "")
    secondary = behavioral_context.get("secondary_preference", "")

    primary_data = LEADERSHIP_STYLES.get(primary, {})
    secondary_data = LEADERSHIP_STYLES.get(secondary, {})

    primary_style = primary_data.get("style", "Emerging Leader")
    secondary_style = secondary_data.get("style", "Developing")

    # Combine strengths from primary and secondary
    strengths = list(primary_data.get("strengths", []))
    if secondary_data.get("strengths"):
        strengths.append(secondary_data["strengths"][0])

    # Blind spots primarily from primary style
    blind_spots = list(primary_data.get("blind_spots", []))

    # Executive presence score based on dimension balance
    dimensions = behavioral_context.get("dimensions", {})
    scores = [dimensions.get(d, 50) for d in ["gold", "green", "blue", "red"]]
    if scores:
        # Higher balance = higher executive presence potential
        avg = sum(scores) / len(scores)
        spread = max(scores) - min(scores)
        # Balanced profiles (low spread) score higher on presence
        # Scale: 100-spread difference mapped to 0-1
        presence = max(0.3, min(1.0, (100 - spread) / 100 + 0.2))
    else:
        presence = 0.5

    description = primary_data.get("description", "")

    logger.info(
        f"Ascend: analyzed leadership signature for user {user_id} "
        f"({primary_style} / {secondary_style})"
    )

    return LeadershipSignature(
        user_id=user_id,
        primary_style=primary_style,
        secondary_style=secondary_style,
        strengths=strengths,
        blind_spots=blind_spots,
        executive_presence_score=round(presence, 2),
        style_description=description,
    )


def assess_team_compatibility(
    leader_context: Optional[dict[str, Any]],
    team_contexts: Optional[list[dict[str, Any]]] = None,
    leader_id: str = "",
) -> TeamCompatibility:
    """
    Assess behavioral compatibility between a leader and their team members.

    Identifies friction areas, synergies, and actionable recommendations.

    Pure function: no side effects, fully testable.
    """
    effective_team = team_contexts or []

    if not leader_context:
        return TeamCompatibility(
            leader_id=leader_id,
            team_members=[],
            compatibility_score=0.0,
            friction_areas=["Leader behavioral profile not available"],
            synergies=[],
            recommendations=["Complete a PRISM assessment to enable team analysis"],
        )

    leader_primary = leader_context.get("primary_preference", "")
    member_ids = []
    synergies = []
    friction_areas = []
    recommendations = []

    # Complementary and friction pairings
    complementary = {
        "gold": ["blue"],      # structure + analysis
        "green": ["red"],      # people + action
        "blue": ["gold"],      # analysis + structure
        "red": ["green"],      # action + people
    }
    tension = {
        "gold": ["red"],       # structure vs speed
        "green": ["blue"],     # feeling vs thinking
        "blue": ["green"],     # thinking vs feeling
        "red": ["gold"],       # speed vs structure
    }

    for member in effective_team:
        member_id = member.get("user_id", "unknown")
        member_ids.append(member_id)
        member_primary = member.get("primary_preference", "")

        if member_primary in complementary.get(leader_primary, []):
            synergies.append(
                f"Leader ({leader_primary.title()}) and team member {member_id} "
                f"({member_primary.title()}) have complementary strengths."
            )
        elif member_primary in tension.get(leader_primary, []):
            friction_areas.append(
                f"Potential friction between leader ({leader_primary.title()}) "
                f"and team member {member_id} ({member_primary.title()}) — "
                f"different pacing and priority preferences."
            )
            recommendations.append(
                f"With {member_id}: explicitly discuss working style "
                f"preferences and find shared ground on pace and priorities."
            )

    # Calculate compatibility score
    if not effective_team:
        score = 0.5
    else:
        synergy_ratio = len(synergies) / len(effective_team) if effective_team else 0
        score = round(0.5 + (synergy_ratio * 0.3) - (len(friction_areas) / max(len(effective_team), 1) * 0.2), 2)
        score = max(0.1, min(1.0, score))

    if not recommendations:
        recommendations.append(
            "Schedule a team working-styles conversation to surface "
            "preferences and build mutual understanding."
        )

    logger.info(
        f"Ascend: assessed team compatibility for leader {leader_id} "
        f"({len(effective_team)} members, score={score})"
    )

    return TeamCompatibility(
        leader_id=leader_id,
        team_members=member_ids,
        compatibility_score=score,
        friction_areas=friction_areas,
        synergies=synergies,
        recommendations=recommendations,
    )


def generate_coaching_scenario(
    focus_area: str,
    behavioral_context: Optional[dict[str, Any]] = None,
) -> CoachingScenario:
    """
    Generate a leadership coaching scenario tailored to behavioral context.

    Pure function: no side effects, fully testable.
    """
    primary = ""
    if behavioral_context:
        primary = behavioral_context.get("primary_preference", "")

    # Scenario templates by focus area
    scenarios: dict[str, dict[str, Any]] = {
        "difficult_conversations": {
            "scenario": (
                "A high-performing team member has been consistently missing "
                "deadlines and their work quality is slipping. Other team members "
                "are starting to notice and morale is affected."
            ),
            "challenge": "Balance accountability with empathy in a performance conversation.",
            "questions": [
                "What assumptions are you making about why the performance changed?",
                "How might your behavioral preference affect how you approach this conversation?",
                "What does this person need to hear, and how do they best receive feedback?",
                "What outcome would represent success for both of you?",
                "How will you follow up to ensure sustained improvement?",
            ],
        },
        "strategic_thinking": {
            "scenario": (
                "Your division is performing well on current metrics, but market "
                "conditions are shifting. Senior leadership wants a 3-year strategy "
                "that positions the team for the future."
            ),
            "challenge": "Shift from operational excellence to strategic vision.",
            "questions": [
                "What would you need to stop doing to create space for strategic thinking?",
                "How does your behavioral preference shape how you approach ambiguity?",
                "Who on your team brings perspectives you tend to undervalue?",
                "What would a bold move look like — one that makes you slightly uncomfortable?",
                "How will you communicate a vision that motivates different behavioral styles?",
            ],
        },
        "team_development": {
            "scenario": (
                "You've just been given a new team after a reorganization. The team "
                "members don't know each other well, come from different cultures, "
                "and some are skeptical about the change."
            ),
            "challenge": "Build trust and cohesion in a newly formed team.",
            "questions": [
                "What does your leadership style signal to people who don't know you yet?",
                "How will you create psychological safety in the first 30 days?",
                "What behavioral preferences might clash on this team, and how will you navigate that?",
                "How will you balance establishing your leadership with empowering the team?",
                "What early win could build momentum and shared identity?",
            ],
        },
        "executive_presence": {
            "scenario": (
                "You're preparing to present a major initiative to the board. "
                "Some board members are skeptical, and the initiative requires "
                "significant investment with uncertain returns."
            ),
            "challenge": "Project confidence and credibility in a high-stakes setting.",
            "questions": [
                "What story does the data tell, and how will you make it compelling?",
                "How might your natural behavioral style help or hinder your presentation?",
                "What objections do you anticipate, and how will you address them?",
                "How will you demonstrate conviction while remaining open to challenge?",
                "What does 'executive presence' mean to you — and what would others say about yours?",
            ],
        },
    }

    # Default focus area
    effective_focus = focus_area.lower().replace(" ", "_")
    template = scenarios.get(effective_focus, scenarios.get("difficult_conversations", {}))

    # Personalize based on behavioral context
    coaching_questions = list(template.get("questions", []))
    if primary:
        style_data = LEADERSHIP_STYLES.get(primary, {})
        style_name = style_data.get("style", "your style")
        coaching_questions.append(
            f"As a {style_name}, what is your natural first instinct here — "
            f"and what would happen if you tried a different approach?"
        )

    development_focus = effective_focus.replace("_", " ").title()

    logger.info(f"Ascend: generated coaching scenario (focus={effective_focus})")

    return CoachingScenario(
        scenario=template.get("scenario", f"A leadership challenge in {focus_area}."),
        challenge=template.get("challenge", f"Develop your {focus_area} capabilities."),
        coaching_questions=coaching_questions,
        development_focus=development_focus,
    )
