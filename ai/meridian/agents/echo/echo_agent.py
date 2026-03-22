from __future__ import annotations

from typing import Any, Optional
from ai.meridian.core.base_agent import BaseAgent
from ai.meridian.core.types import (
    AgentId, AgentTask, AgentResult, AgentCapability,
    OrchestratorId, TaskStatus,
)
from ai.meridian.agents.echo.echo_tools import (
    build_learning_path,
    create_micro_lesson,
)
from prism_inspire.core.log_config import logger


class EchoAgent(BaseAgent):
    """
    Echo — The Patient Educator.

    Adaptive learning paths, micro-learning, competency development.

    Supported actions:
    - create_learning_path: Build a personalized learning path
    - micro_lesson: Deliver a single micro-learning module
    - track_progress: Check and update learning progress
    """

    def __init__(self, llm_provider: Any = None, memory_service: Any = None) -> None:
        super().__init__(AgentId.ECHO)
        self._llm_provider = llm_provider
        self._memory_service = memory_service
        self._progress: dict[str, dict[str, Any]] = {}

    def get_capabilities(self) -> AgentCapability:
        return AgentCapability(
            agent_id=AgentId.ECHO,
            name="Echo",
            tagline="The Patient Educator",
            domain=OrchestratorId.PERSONAL_DEVELOPMENT,
            actions=["create_learning_path", "micro_lesson", "track_progress"],
            description=(
                "Designs personalized learning paths and delivers adaptive "
                "micro-learning. Adapts teaching style to PRISM behavioral preferences."
            ),
        )

    async def process_task(self, task: AgentTask) -> AgentResult:
        handlers = {
            "create_learning_path": self._create_learning_path,
            "micro_lesson": self._micro_lesson,
            "track_progress": self._track_progress,
        }
        handler = handlers.get(task.action)
        if handler is None:
            return AgentResult(
                task_id=task.task_id, agent_id=AgentId.ECHO,
                status=TaskStatus.FAILED,
                output={"error": f"Unknown action: {task.action}"}, confidence=0.0,
            )
        return await handler(task)

    async def _create_learning_path(self, task: AgentTask) -> AgentResult:
        skill_gap = task.parameters.get("skill_gap", "general development")
        current_level = task.parameters.get("current_level", "beginner")
        path = build_learning_path(skill_gap, task.behavioral_context, current_level)

        user_id = task.parameters.get("user_id") or task.context.get("user_id", "")
        if user_id:
            self._progress[user_id] = {"path_id": path.path_id, "completed_modules": 0, "total_modules": len(path.modules)}

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ECHO,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"I've created a learning path for {skill_gap}. "
                    f"It has {len(path.modules)} modules and should take about {path.estimated_duration}. "
                    f"{'Adapted for your style: ' + path.behavioral_adaptation if path.behavioral_adaptation else ''}"
                ),
                "response": (
                    f"Great news — your personalized learning path for **{skill_gap}** is ready! "
                    f"We'll work through {len(path.modules)} bite-sized modules together. "
                    f"No rush — we go at your pace."
                ),
                "learning_path": path.model_dump(),
            },
            confidence=0.85,
            reasoning=f"Learning path created for {skill_gap}",
        )

    async def _micro_lesson(self, task: AgentTask) -> AgentResult:
        topic = task.parameters.get("topic", "skill development")
        lesson = create_micro_lesson(topic, task.behavioral_context)

        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ECHO,
            status=TaskStatus.COMPLETED,
            output={
                "summary": f"Here's a quick lesson on {topic}. {lesson.content}",
                "response": (
                    f"Let's spend a few minutes on **{topic}**. "
                    f"{lesson.content}\n\n"
                    f"Key takeaways:\n" +
                    "\n".join(f"- {t}" for t in lesson.key_takeaways) +
                    f"\n\nPractice: {lesson.practice_exercise}"
                ),
                "micro_lesson": lesson.model_dump(),
            },
            confidence=0.85,
        )

    async def _track_progress(self, task: AgentTask) -> AgentResult:
        user_id = task.parameters.get("user_id") or task.context.get("user_id", "")
        progress = self._progress.get(user_id)
        if not progress:
            return AgentResult(
                task_id=task.task_id, agent_id=AgentId.ECHO,
                status=TaskStatus.COMPLETED,
                output={
                    "summary": "You don't have an active learning path yet. Want me to create one?",
                    "progress": None,
                },
                confidence=0.90,
            )
        return AgentResult(
            task_id=task.task_id, agent_id=AgentId.ECHO,
            status=TaskStatus.COMPLETED,
            output={
                "summary": (
                    f"You've completed {progress['completed_modules']} of "
                    f"{progress['total_modules']} modules. Keep going!"
                ),
                "progress": progress,
            },
            confidence=0.90,
        )
