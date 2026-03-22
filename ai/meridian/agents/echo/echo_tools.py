from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
import uuid


class LearningPath(BaseModel):
    """A personalized learning path."""
    path_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    modules: list[dict[str, Any]] = Field(default_factory=list)
    estimated_duration: str = ""
    difficulty: str = "beginner"
    competencies: list[str] = Field(default_factory=list)
    behavioral_adaptation: str = ""


class MicroLesson(BaseModel):
    """A single micro-learning module."""
    lesson_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str
    duration_minutes: int = 5
    key_takeaways: list[str] = Field(default_factory=list)
    practice_exercise: Optional[str] = None
    competency: str = ""


def build_learning_path(
    skill_gap: str,
    behavioral_context: Optional[dict[str, Any]] = None,
    current_level: str = "beginner",
) -> LearningPath:
    """Build a learning path based on skill gap and behavioral preferences."""
    primary = ""
    adaptation = ""
    if behavioral_context:
        primary = behavioral_context.get("primary_preference", "")
        style_map = {
            "gold": "structured modules with checklists and clear milestones",
            "green": "collaborative exercises and discussion-based learning",
            "blue": "data-driven case studies and analytical frameworks",
            "red": "action-oriented challenges with immediate application",
        }
        adaptation = style_map.get(primary, "balanced mix of learning approaches")

    modules = [
        {"order": 1, "title": f"Foundations of {skill_gap}", "type": "concept", "duration": "10 min"},
        {"order": 2, "title": "Core Principles", "type": "theory", "duration": "15 min"},
        {"order": 3, "title": "Practical Application", "type": "exercise", "duration": "20 min"},
        {"order": 4, "title": "Safe Practice Environment", "type": "simulation", "duration": "15 min"},
        {"order": 5, "title": "Review & Reinforcement", "type": "assessment", "duration": "10 min"},
    ]

    return LearningPath(
        title=f"Learning Path: {skill_gap}",
        description=f"A personalized path to develop your {skill_gap} skills.",
        modules=modules,
        estimated_duration="70 minutes across 5 sessions",
        difficulty=current_level,
        competencies=[skill_gap],
        behavioral_adaptation=adaptation,
    )


def create_micro_lesson(
    topic: str,
    behavioral_context: Optional[dict[str, Any]] = None,
) -> MicroLesson:
    """Create an adaptive micro-lesson."""
    primary = behavioral_context.get("primary_preference", "") if behavioral_context else ""

    exercise_map = {
        "gold": f"Create a structured checklist for applying {topic} in your next project.",
        "green": f"Discuss {topic} with a colleague and share your key takeaway.",
        "blue": f"Find one data point that supports the importance of {topic} in your work.",
        "red": f"Apply one concept from {topic} before end of day today.",
    }

    return MicroLesson(
        title=f"Micro-lesson: {topic}",
        content=f"Let's explore {topic} together in a way that fits your learning style.",
        duration_minutes=5,
        key_takeaways=[
            f"Core concept of {topic}",
            "How it applies to your current role",
            "One action you can take today",
        ],
        practice_exercise=exercise_map.get(primary, f"Reflect on how {topic} applies to your work."),
        competency=topic,
    )
