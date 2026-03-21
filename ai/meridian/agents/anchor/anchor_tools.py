from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class EnergyLevel(str, Enum):
    CRITICAL = "critical"
    LOW = "low"
    MODERATE = "moderate"
    GOOD = "good"
    HIGH = "high"


class StressCheckIn(BaseModel):
    """A stress/energy check-in record."""
    checkin_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    energy_level: EnergyLevel
    stress_score: int = Field(ge=1, le=10, description="1=calm, 10=overwhelmed")
    sleep_quality: Optional[int] = Field(None, ge=1, le=5)
    notes: str = ""
    is_private: bool = True  # ALWAYS True — never surfaced to management


class RecoveryProtocol(BaseModel):
    """A personalized recovery protocol."""
    title: str
    description: str
    steps: list[str] = Field(default_factory=list)
    duration: str = ""
    behavioral_adaptation: str = ""


def assess_burnout_risk(
    stress_score: int,
    energy_level: EnergyLevel,
    recent_scores: Optional[list[int]] = None,
) -> dict[str, Any]:
    """Assess burnout risk based on current and historical indicators."""
    risk_level = "low"
    if stress_score >= 8 or energy_level in (EnergyLevel.CRITICAL, EnergyLevel.LOW):
        risk_level = "high"
    elif stress_score >= 6 or energy_level == EnergyLevel.MODERATE:
        risk_level = "moderate"

    # Check trend if history available
    trending_worse = False
    if recent_scores and len(recent_scores) >= 3:
        trending_worse = all(recent_scores[i] <= recent_scores[i + 1] for i in range(len(recent_scores) - 1))

    if trending_worse and risk_level != "high":
        risk_level = "moderate" if risk_level == "low" else "high"

    recommendations = {
        "low": ["Continue current self-care practices", "Schedule a check-in next week"],
        "moderate": [
            "Identify your top energy drain this week",
            "Block 30 minutes of recovery time today",
            "Consider which commitments can be deferred",
        ],
        "high": [
            "Take a recovery break as soon as possible",
            "Talk to someone you trust about how you're feeling",
            "Reduce non-essential commitments this week",
            "Focus on sleep quality tonight",
        ],
    }

    return {
        "risk_level": risk_level,
        "stress_score": stress_score,
        "energy_level": energy_level.value,
        "trending_worse": trending_worse,
        "recommendations": recommendations.get(risk_level, []),
        "needs_escalation": stress_score >= 9 or energy_level == EnergyLevel.CRITICAL,
    }


def build_recovery_protocol(
    risk_level: str,
    behavioral_context: Optional[dict[str, Any]] = None,
) -> RecoveryProtocol:
    """Build a personalized recovery protocol based on risk and PRISM profile."""
    primary = behavioral_context.get("primary_preference", "") if behavioral_context else ""

    base_steps = {
        "high": [
            "Pause and take three deep breaths right now",
            "Identify the single biggest stressor and write it down",
            "Set one boundary today — say no to one non-essential request",
            "Schedule 8 hours of sleep tonight as non-negotiable",
            "Move your body for 10 minutes — walk, stretch, anything",
        ],
        "moderate": [
            "Take a 15-minute break from screens",
            "Identify what's draining your energy most",
            "Plan one thing you enjoy for today",
            "Review your week — what can be moved or delegated?",
        ],
        "low": [
            "Keep doing what you're doing — your self-care is working",
            "Consider what's helping and do more of it",
        ],
    }

    prism_additions = {
        "gold": "Create a structured recovery schedule with specific times blocked for rest.",
        "green": "Reach out to a supportive friend or colleague — connection recharges you.",
        "blue": "Journal about what's causing stress — analytical processing helps you decompress.",
        "red": "Give yourself explicit permission to rest. Recovery IS productive action.",
    }

    steps = base_steps.get(risk_level, base_steps["moderate"])
    adaptation = prism_additions.get(primary, "")
    if adaptation:
        steps.append(adaptation)

    return RecoveryProtocol(
        title=f"Recovery Protocol — {risk_level.title()} Priority",
        description="A personalized recovery plan for your current stress level.",
        steps=steps,
        duration="This week" if risk_level == "high" else "Ongoing",
        behavioral_adaptation=adaptation,
    )
