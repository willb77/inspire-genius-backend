from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from ai.meridian.core.types import (
    AgentTask, AgentResult, AgentCapability, AgentId, TaskStatus
)
from prism_inspire.core.log_config import logger


class BaseAgent(ABC):
    """
    Base class for all Meridian specialist agents.

    Every agent receives behavioral context from Aura (the intelligence backbone)
    and must implement processTask(), getCapabilities(), and reportStatus().
    """

    def __init__(self, agent_id: AgentId):
        self._agent_id = agent_id
        self._is_active = True

    @property
    def agent_id(self) -> AgentId:
        return self._agent_id

    @abstractmethod
    async def process_task(self, task: AgentTask) -> AgentResult:
        """
        Process an assigned task and return results.
        The task.behavioral_context contains Aura's output when available.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> AgentCapability:
        """Return this agent's capabilities and supported actions."""
        ...

    def report_status(self) -> dict:
        """Report current agent status."""
        return {
            "agent_id": self._agent_id.value,
            "is_active": self._is_active,
            "capabilities": self.get_capabilities().model_dump(),
        }

    def _inject_behavioral_context(self, task: AgentTask) -> AgentTask:
        """
        Ensure behavioral context from Aura is available in the task.
        All agents consult Aura's behavioral output.
        """
        if task.behavioral_context is None:
            logger.warning(
                f"Agent {self._agent_id.value} processing task {task.task_id} "
                "without behavioral context from Aura"
            )
        return task

    async def _execute(self, task: AgentTask) -> AgentResult:
        """Internal execution wrapper with logging and context injection."""
        logger.info(f"Agent {self._agent_id.value} starting task {task.task_id}: {task.action}")
        task = self._inject_behavioral_context(task)
        try:
            result = await self.process_task(task)
            logger.info(
                f"Agent {self._agent_id.value} completed task {task.task_id} "
                f"with confidence {result.confidence:.2f}"
            )
            return result
        except Exception as e:
            logger.error(f"Agent {self._agent_id.value} failed task {task.task_id}: {e}")
            return AgentResult(
                task_id=task.task_id,
                agent_id=self._agent_id,
                status=TaskStatus.FAILED,
                output={"error": str(e)},
                confidence=0.0,
                reasoning=f"Task failed with error: {e}",
            )
