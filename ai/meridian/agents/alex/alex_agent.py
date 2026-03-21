from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.alex.alex_tools import (
    CareerExploration,
    AcademicPlan,
    explore_careers,
    build_academic_plan,
    is_prism_eligible,
)
from prism_inspire.core.log_config import logger


class AlexAgent(BaseAgent):
    """
    Alex — The Student Success Advisor.

    Age-appropriate academic and career guidance for students from
    middle school through graduate programs.

    Supported actions:
    - career_exploration: Age-appropriate career family exploration
    - academic_plan: Study strategies and course recommendations
    - prism_assessment: Check eligibility and interpret if available
    """

    def __init__(
        self,
        llm_provider: Any = None,
        memory_service: Any = None,
    ) -> None:
        super().__init__(AgentId.ALEX)
        self._llm_provider = llm_provider
        self._memory_service = memory_service

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.ALEX,
            name="Alex",
            tagline="The Student Success Advisor",
            domain=OrchestratorId.STRATEGIC_ADVISORY,
            actions=[
                "career_exploration",
                "academic_plan",
                "prism_assessment",
            ],
            description=(
                "Age-appropriate academic and career guidance for students. "
                "Adapts communication style from playful curiosity (middle school) "
                "to strategic advising (university/graduate). Always encouraging, "
                "always honest, always age-appropriate."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        """Route to the appropriate handler based on task action."""
        handlers = {
            "career_exploration": self._career_exploration,
            "academic_plan": self._academic_plan,
            "prism_assessment": self._prism_assessment,
        }

        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ALEX,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"},
                confidence=0.0,
                reasoning=f"Action '{task.action}' is not supported by Alex",
            )

        return await handler(task)

    async def _career_exploration(self, task: AgentTask) -> AgentResult:
        """Age-appropriate career family exploration."""
        student_id = task.parameters.get("student_id") or task.context.get("user_id", "")
        interests = task.parameters.get("interests", [])
        age_group = task.parameters.get("age_group", "middle_school")
        behavioral_context = task.behavioral_context

        exploration = explore_careers(
            interests=interests,
            behavioral_context=behavioral_context,
            age_group=age_group,
            student_id=student_id,
        )

        # Build age-appropriate narrative
        if age_group == "middle_school":
            narrative = self._build_middle_school_narrative(exploration, interests)
        else:
            narrative = self._build_university_narrative(exploration, interests)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ALEX,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "exploration": exploration.model_dump(),
            },
            confidence=0.82,
            reasoning=f"Career exploration for {age_group} student",
        )

    async def _academic_plan(self, task: AgentTask) -> AgentResult:
        """Build study strategies and course recommendations."""
        student_id = task.parameters.get("student_id") or task.context.get("user_id", "")
        goals = task.parameters.get("goals", [])
        grade_level = task.parameters.get("grade_level", "")

        if not goals:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ALEX,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "Let's build your academic plan! What are your goals? "
                        "They can be anything — getting better at a subject, "
                        "preparing for college, exploring a career, or just "
                        "figuring out what you enjoy."
                    ),
                    "response": (
                        "I'd love to help you plan your academics. "
                        "What goals would you like to work toward? "
                        "Share as many as you'd like and we'll build a plan together."
                    ),
                    "needs_input": True,
                },
                confidence=0.90,
                reasoning="Awaiting student goals for academic planning",
            )

        plan = build_academic_plan(
            goals=goals,
            grade_level=grade_level,
            student_id=student_id,
        )

        # Build narrative
        narrative_parts = ["Here's your personalized academic plan:", ""]

        narrative_parts.append("**Your Goals:**")
        for goal in plan.goals:
            narrative_parts.append(f"- {goal}")

        narrative_parts.append("")
        narrative_parts.append("**Recommended Courses / Subjects:**")
        for course in plan.recommended_courses:
            narrative_parts.append(f"- {course}")

        narrative_parts.append("")
        narrative_parts.append("**Study Strategies That Work:**")
        for strategy in plan.study_strategies:
            narrative_parts.append(f"- {strategy}")

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ALEX,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "academic_plan": plan.model_dump(),
            },
            confidence=0.83,
            reasoning=f"Academic plan built for grade level: {grade_level or 'unspecified'}",
        )

    async def _prism_assessment(self, task: AgentTask) -> AgentResult:
        """Check PRISM eligibility and interpret results if available."""
        student_id = task.parameters.get("student_id") or task.context.get("user_id", "")
        age_or_grade = task.parameters.get("age_or_grade", 0)
        behavioral_context = task.behavioral_context

        # Check eligibility first
        if age_or_grade and not is_prism_eligible(age_or_grade):
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ALEX,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "The PRISM behavioral assessment is available starting "
                        "in 8th grade (around age 13-14). You're not quite there "
                        "yet, but that's totally fine! For now, we can explore "
                        "careers based on your interests and what you enjoy."
                    ),
                    "response": (
                        "PRISM isn't available for your grade level yet — it starts "
                        "in 8th grade. But that's no problem at all! We can still "
                        "explore awesome career paths based on what you love to do. "
                        "What are you most interested in?"
                    ),
                    "prism_eligible": False,
                    "has_assessment": False,
                },
                confidence=0.95,
                reasoning=f"Student not PRISM eligible (age_or_grade={age_or_grade})",
            )

        # Eligible but no assessment data
        if not behavioral_context:
            return AgentResult(
                task_id=task.task_id,
                agent_id=AgentId.ALEX,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": (
                        "You're eligible for a PRISM behavioral assessment! "
                        "It's a quick questionnaire that helps us understand your "
                        "natural strengths and preferences. Once you complete it, "
                        "I can give you much more personalized career and academic "
                        "guidance."
                    ),
                    "response": (
                        "Great news — you can take the PRISM assessment! It takes "
                        "about 15-20 minutes and helps us understand how you "
                        "naturally think and work. Want to get started?"
                    ),
                    "prism_eligible": True,
                    "has_assessment": False,
                },
                confidence=0.90,
                reasoning="Student is PRISM eligible but has no assessment",
            )

        # Has assessment — interpret it
        primary = behavioral_context.get("primary_preference", "")
        secondary = behavioral_context.get("secondary_preference", "")
        insights = behavioral_context.get("insights", [])

        narrative_parts = [
            "Here's what your PRISM profile tells us about your strengths:",
            "",
            f"Your strongest preference is **{primary.title()}**, "
            f"with **{secondary.title()}** as your secondary.",
            "",
        ]

        if insights:
            narrative_parts.append(insights[0])
            narrative_parts.append("")

        narrative_parts.append(
            "Remember — this shows your natural preferences, not your limits. "
            "You can develop any skill with practice and effort. This just helps "
            "us understand where you'll feel most naturally energized."
        )

        narrative = "\n".join(narrative_parts)

        return AgentResult(
            task_id=task.task_id,
            agent_id=AgentId.ALEX,
            status=TaskStatus.COMPLETED,
            output={
                "summary": narrative,
                "response": narrative,
                "prism_eligible": True,
                "has_assessment": True,
                "primary_preference": primary,
                "secondary_preference": secondary,
            },
            confidence=0.85,
            reasoning="PRISM assessment interpreted for student",
        )

    # ------------------------------------------------------------------
    # Narrative helpers
    # ------------------------------------------------------------------

    def _build_middle_school_narrative(
        self, exploration: CareerExploration, interests: list[str]
    ) -> str:
        """Build a fun, encouraging narrative for middle school students."""
        parts = []

        if interests:
            parts.append(
                f"Cool — you're into {', '.join(interests)}! "
                "Let's see what career areas connect to those interests."
            )
        else:
            parts.append(
                "Let's explore some career areas together! "
                "There are so many cool things out there."
            )

        parts.append("")
        parts.append("**Career Areas to Explore:**")
        for fam in exploration.career_families:
            parts.append(f"- {fam}")

        parts.append("")
        parts.append("**Fun Things to Try:**")
        for act in exploration.exploration_activities[:3]:
            parts.append(f"- {act}")

        parts.append("")
        parts.append(
            "Remember, you don't have to pick anything now. "
            "The goal is to explore and see what excites you!"
        )

        return "\n".join(parts)

    def _build_university_narrative(
        self, exploration: CareerExploration, interests: list[str]
    ) -> str:
        """Build a strategic narrative for university/graduate students."""
        parts = []

        if interests:
            parts.append(
                f"Based on your interests in {', '.join(interests)}, "
                "here are career families worth exploring strategically."
            )
        else:
            parts.append(
                "Here are career families that align with your profile. "
                "Let's think about these strategically."
            )

        parts.append("")
        parts.append("**Career Families:**")
        for fam in exploration.career_families:
            parts.append(f"- {fam}")

        parts.append("")
        parts.append("**Strategic Next Steps:**")
        for step in exploration.exploration_activities[:3]:
            parts.append(f"- {step}")

        if exploration.next_steps:
            parts.append("")
            for step in exploration.next_steps:
                parts.append(f"- {step}")

        return "\n".join(parts)
