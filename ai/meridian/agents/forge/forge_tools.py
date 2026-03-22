from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class ConflictAnalysis(BaseModel):
    """Analysis of a conflict situation between two parties."""
    analysis_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_profile_summary: str = ""
    counterpart_profile_summary: str = ""
    dynamic: str = ""
    friction_points: list[str] = Field(default_factory=list)
    common_ground: list[str] = Field(default_factory=list)
    recommended_approach: str = ""


class CommunicationPlaybook(BaseModel):
    """A communication playbook for a specific interaction."""
    title: str
    context: str = ""
    opening_scripts: list[str] = Field(default_factory=list)
    key_phrases: list[str] = Field(default_factory=list)
    phrases_to_avoid: list[str] = Field(default_factory=list)
    body_language_tips: list[str] = Field(default_factory=list)
    debrief_questions: list[str] = Field(default_factory=list)


class MeetingBriefing(BaseModel):
    """Pre-meeting briefing with stakeholder insights."""
    briefing_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    meeting_purpose: str
    attendee_insights: list[dict[str, Any]] = Field(default_factory=list)
    recommended_approach: str = ""
    talking_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


def analyze_conflict(
    user_context: Optional[dict[str, Any]],
    counterpart_context: Optional[dict[str, Any]],
    situation: str,
) -> ConflictAnalysis:
    """Analyze conflict dynamics between two PRISM profiles."""
    user_primary = user_context.get("primary_preference", "unknown") if user_context else "unknown"
    counterpart_primary = counterpart_context.get("primary_preference", "unknown") if counterpart_context else "unknown"

    friction_map = {
        ("gold", "red"): ["Gold's need for process vs Red's bias for speed", "Detail orientation vs big-picture focus"],
        ("green", "blue"): ["Green's relationship focus vs Blue's task focus", "Emotional considerations vs analytical approach"],
        ("red", "green"): ["Red's directness may feel aggressive to Green", "Green's consensus-building may frustrate Red's pace"],
        ("blue", "gold"): ["Blue's questioning may feel like criticism of Gold's systems", "Gold's structure may feel rigid to Blue's exploration"],
    }

    common_map = {
        ("gold", "blue"): ["Both value quality and thoroughness", "Shared appreciation for preparation"],
        ("green", "red"): ["Both are action-oriented in different ways", "Shared passion and energy"],
        ("gold", "green"): ["Both care about people within structure", "Shared reliability"],
        ("blue", "red"): ["Both are goal-oriented", "Shared decisiveness"],
    }

    key = (user_primary, counterpart_primary)
    reverse_key = (counterpart_primary, user_primary)
    friction = friction_map.get(key) or friction_map.get(reverse_key) or [f"Potential style differences between {user_primary} and {counterpart_primary}"]
    common = common_map.get(key) or common_map.get(reverse_key) or ["Shared commitment to the goal at hand"]

    approach_map = {
        "gold": "Present your perspective with clear structure and supporting details",
        "green": "Lead with empathy and relationship acknowledgment before the issue",
        "blue": "Use data and logical reasoning to support your position",
        "red": "Be direct and solution-focused — get to the point quickly",
    }

    return ConflictAnalysis(
        user_profile_summary=f"Your {user_primary.title()} preference shapes how you approach conflict",
        counterpart_profile_summary=f"Their {counterpart_primary.title()} preference means they value {approach_map.get(counterpart_primary, 'different things')}",
        dynamic=f"{user_primary.title()}-{counterpart_primary.title()} dynamic",
        friction_points=friction,
        common_ground=common,
        recommended_approach=approach_map.get(counterpart_primary, "Adapt your communication style to their preferences"),
    )


def build_communication_playbook(
    situation: str,
    user_context: Optional[dict[str, Any]],
    counterpart_context: Optional[dict[str, Any]],
) -> CommunicationPlaybook:
    """Build a communication playbook for a specific interaction."""
    counterpart_primary = counterpart_context.get("primary_preference", "") if counterpart_context else ""

    scripts = {
        "gold": [
            f"I'd like to walk through {situation} step by step so we're aligned.",
            "I've prepared an overview — can I share the key points?",
        ],
        "green": [
            f"I value our relationship, and I want to discuss {situation} openly.",
            "I'd love to hear your perspective before I share mine.",
        ],
        "blue": [
            f"I've been looking at the data around {situation} and have some observations.",
            "What does the evidence tell us about the best path forward?",
        ],
        "red": [
            f"I want to address {situation} directly so we can move forward.",
            "Here's what I think we should do, and I'd like your input.",
        ],
    }

    avoid = {
        "gold": ["Springing surprises", "Skipping over details", "Appearing disorganized"],
        "green": ["Being blunt without empathy", "Ignoring feelings", "Public criticism"],
        "blue": ["Using unsupported claims", "Being vague", "Emotional appeals without evidence"],
        "red": ["Long preambles", "Indecisiveness", "Excessive hedging"],
    }

    return CommunicationPlaybook(
        title=f"Playbook: {situation}",
        context=f"Adapted for their {counterpart_primary.title()} communication style" if counterpart_primary else "",
        opening_scripts=scripts.get(counterpart_primary, [f"Let's talk about {situation}."]),
        key_phrases=[
            "I appreciate your perspective on this",
            "Help me understand your thinking",
            "What would a good outcome look like for you?",
        ],
        phrases_to_avoid=avoid.get(counterpart_primary, ["Dismissive language", "Absolute statements"]),
        body_language_tips=[
            "Maintain open posture",
            "Make appropriate eye contact",
            "Nod to show understanding (not necessarily agreement)",
        ],
        debrief_questions=[
            "How did the conversation go compared to what I prepared for?",
            "What worked well? What would I do differently?",
            "Is there a follow-up action needed?",
        ],
    )


def build_meeting_briefing(
    meeting_purpose: str,
    attendees: list[dict[str, Any]],
) -> MeetingBriefing:
    """Build a pre-meeting briefing with stakeholder insights."""
    insights = []
    for attendee in attendees:
        primary = attendee.get("primary_preference", "")
        name = attendee.get("name", "Attendee")
        insight = {
            "name": name,
            "style": primary,
            "tip": {
                "gold": f"{name} appreciates agendas and preparation. Come organized.",
                "green": f"{name} values inclusion. Make space for their input.",
                "blue": f"{name} wants evidence. Bring data to support your points.",
                "red": f"{name} wants action. Be concise and solution-oriented.",
            }.get(primary, f"Adapt to {name}'s communication preferences."),
        }
        insights.append(insight)

    return MeetingBriefing(
        meeting_purpose=meeting_purpose,
        attendee_insights=insights,
        recommended_approach="Prepare key points, anticipate questions, and adapt your style per attendee.",
        talking_points=[f"Objective: {meeting_purpose}", "Key data points", "Proposed next steps"],
        risks=["Misaligned expectations", "Time overrun if not managed"],
    )
