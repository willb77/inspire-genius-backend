from __future__ import annotations

"""
Meridian Onboarding Experience — warm, empowering first interaction.

Uses "we" language, navigation metaphors, and natural systems imagery
per the Ecosystem Guide. Never just diagnoses — always provides pathways forward.
"""

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import uuid


class OnboardingStage(str, Enum):
    WELCOME = "welcome"
    PRISM_INTRO = "prism_intro"
    ASSESSMENT_COMPLETE = "assessment_complete"
    PROFILE_WALKTHROUGH = "profile_walkthrough"
    GOAL_SETTING = "goal_setting"
    READY = "ready"


class OnboardingState(BaseModel):
    """Tracks where a user is in the onboarding flow."""
    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stage: OnboardingStage = OnboardingStage.WELCOME
    has_prism: bool = False
    profile_data: Optional[dict[str, Any]] = None
    goals: list[str] = Field(default_factory=list)


# Navigation and natural systems metaphors
MERIDIAN_WELCOME = (
    "Welcome — I'm Meridian, your personal guide to the intersection of "
    "potential and purpose. Think of me as a compass that helps you navigate "
    "your professional journey.\n\n"
    "We're going to explore what makes you unique — not to put you in a box, "
    "but to help you understand your natural strengths and the many paths "
    "available to you.\n\n"
    "Let's begin this journey together."
)

PRISM_INTRO = (
    "The first step on our journey is a PRISM Brain Mapping assessment. "
    "This isn't a test — there are no right or wrong answers. It's more like "
    "a mirror that reflects your natural behavioral preferences.\n\n"
    "PRISM maps four dimensions of how you engage with the world:\n"
    "- **Gold** — your structured, detail-oriented side\n"
    "- **Green** — your empathetic, people-focused side\n"
    "- **Blue** — your analytical, data-driven side\n"
    "- **Red** — your action-oriented, results-driven side\n\n"
    "Everyone has all four — we'll explore how yours blend together. "
    "The assessment takes about 10-15 minutes. Ready when you are."
)

PROFILE_WALKTHROUGH_TEMPLATE = (
    "Let's explore your Behavioral Preference Map together.\n\n"
    "Your strongest preference is **{primary}** — {primary_desc}. "
    "This is complemented by your **{secondary}** side — {secondary_desc}.\n\n"
    "{insight}\n\n"
    "Remember: these are preferences, not limits. You have the capacity "
    "to flex into any dimension when the situation calls for it. "
    "We'll work together to help you leverage your natural strengths "
    "while expanding your range.\n\n"
    "What aspect of your profile would you like to explore further?"
)

GOAL_SETTING_PROMPT = (
    "Now that we have a clearer picture of your behavioral landscape, "
    "let's chart a course together. What areas are you most interested "
    "in developing?\n\n"
    "Some possibilities based on your profile:\n"
    "{suggestions}\n\n"
    "There's no wrong answer here — this is your journey, and we'll "
    "adjust the route as we go."
)

ONBOARDING_COMPLETE = (
    "You're all set! Here's what we've mapped so far:\n\n"
    "- **Your behavioral profile**: {primary}-{secondary} combination\n"
    "- **Your focus areas**: {goals}\n\n"
    "I'm here whenever you need guidance — whether it's a quick check-in "
    "or a deep dive into career strategy. Think of me as your always-available "
    "mentor.\n\n"
    "What would you like to explore first?"
)

DIMENSION_DESCRIPTIONS = {
    "gold": "you bring structure, reliability, and attention to detail",
    "green": "you connect with people naturally and build strong relationships",
    "blue": "you analyze situations deeply and make evidence-based decisions",
    "red": "you take decisive action and drive results forward",
}

GOAL_SUGGESTIONS = {
    "gold": ["Developing leadership flexibility", "Strategic delegation skills", "Embracing ambiguity"],
    "green": ["Strengthening difficult conversations", "Data-driven decision making", "Setting boundaries"],
    "blue": ["Executive communication", "Building rapport quickly", "Decisive action under uncertainty"],
    "red": ["Active listening", "Consensus building", "Patience with process"],
}


class OnboardingFlow:
    """
    Manages the new user onboarding experience through Meridian.

    Flow: Welcome → PRISM Intro → Assessment → Profile Walkthrough → Goal Setting → Ready
    """

    def __init__(self) -> None:
        self._states: dict[str, OnboardingState] = {}

    def start(self, user_id: str) -> dict[str, Any]:
        """Start onboarding for a new user."""
        state = OnboardingState(user_id=user_id)
        self._states[user_id] = state
        return {
            "stage": state.stage.value,
            "session_id": state.session_id,
            "message": MERIDIAN_WELCOME,
        }

    def introduce_prism(self, user_id: str) -> dict[str, Any]:
        """Introduce PRISM assessment."""
        state = self._get_state(user_id)
        state.stage = OnboardingStage.PRISM_INTRO
        return {
            "stage": state.stage.value,
            "message": PRISM_INTRO,
        }

    def complete_assessment(
        self, user_id: str, profile_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Process completed PRISM assessment."""
        state = self._get_state(user_id)
        state.stage = OnboardingStage.ASSESSMENT_COMPLETE
        state.has_prism = True
        state.profile_data = profile_data
        return {
            "stage": state.stage.value,
            "message": "Wonderful — your assessment is complete! Let's explore what it reveals.",
            "has_prism": True,
        }

    def walkthrough_profile(
        self, user_id: str, profile_data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Walk through the user's Behavioral Preference Map."""
        state = self._get_state(user_id)
        data = profile_data or state.profile_data or {}
        state.stage = OnboardingStage.PROFILE_WALKTHROUGH

        primary = data.get("primary_preference", "gold")
        secondary = data.get("secondary_preference", "green")
        insights = data.get("insights", [])

        message = PROFILE_WALKTHROUGH_TEMPLATE.format(
            primary=primary.title(),
            primary_desc=DIMENSION_DESCRIPTIONS.get(primary, "a unique blend of strengths"),
            secondary=secondary.title(),
            secondary_desc=DIMENSION_DESCRIPTIONS.get(secondary, "complementary qualities"),
            insight=insights[0] if insights else "Your unique combination opens many doors.",
        )
        return {
            "stage": state.stage.value,
            "message": message,
            "profile": data,
        }

    def set_goals(self, user_id: str, goals: Optional[list[str]] = None) -> dict[str, Any]:
        """Guide goal setting based on profile."""
        state = self._get_state(user_id)
        state.stage = OnboardingStage.GOAL_SETTING

        primary = (state.profile_data or {}).get("primary_preference", "gold")
        suggestions = GOAL_SUGGESTIONS.get(primary, ["Personal growth", "Career development"])

        if goals:
            state.goals = goals

        formatted = "\n".join(f"- {s}" for s in suggestions)
        message = GOAL_SETTING_PROMPT.format(suggestions=formatted)
        return {
            "stage": state.stage.value,
            "message": message,
            "suggested_goals": suggestions,
        }

    def complete(self, user_id: str, goals: Optional[list[str]] = None) -> dict[str, Any]:
        """Complete onboarding."""
        state = self._get_state(user_id)
        if goals:
            state.goals = goals
        state.stage = OnboardingStage.READY

        primary = (state.profile_data or {}).get("primary_preference", "unknown")
        secondary = (state.profile_data or {}).get("secondary_preference", "unknown")
        goal_text = ", ".join(state.goals) if state.goals else "to be defined together"

        message = ONBOARDING_COMPLETE.format(
            primary=primary.title(),
            secondary=secondary.title(),
            goals=goal_text,
        )
        return {
            "stage": state.stage.value,
            "message": message,
            "is_complete": True,
        }

    def get_state(self, user_id: str) -> Optional[dict[str, Any]]:
        """Get current onboarding state."""
        state = self._states.get(user_id)
        if state is None:
            return None
        return state.model_dump()

    def _get_state(self, user_id: str) -> OnboardingState:
        if user_id not in self._states:
            self._states[user_id] = OnboardingState(user_id=user_id)
        return self._states[user_id]
