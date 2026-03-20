from __future__ import annotations

"""
Meridian Collaboration Service — inter-agent structured messaging.

Handles:
- Task handoff with full context preservation
- Status updates and result passing between agents
- DAG execution coordination
- Agent-to-agent communication without direct coupling
"""

from datetime import datetime
from typing import Any, Callable, Awaitable, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
from ai.meridian.core.types import AgentId, TaskStatus
import uuid


class TaskMessage(BaseModel):
    """A structured message passed between agents."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: AgentId
    to_agent: AgentId
    message_type: str  # "task_handoff", "status_update", "result", "request"
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None  # links related messages
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CollaborationService:
    """
    Inter-agent structured messaging and coordination service.

    Provides:
    - Task handoff with full context preservation
    - Status updates and result passing
    - DAG execution coordination
    - Pub/sub style message routing
    """

    def __init__(self) -> None:
        # Message handlers per agent
        self._handlers: dict[AgentId, list[Callable[[TaskMessage], Awaitable[None]]]] = {}
        # Message log for audit trail
        self._message_log: list[TaskMessage] = []
        # Pending handoffs awaiting acknowledgment
        self._pending_handoffs: dict[str, TaskMessage] = {}

    def subscribe(
        self,
        agent_id: AgentId,
        handler: Callable[[TaskMessage], Awaitable[None]],
    ) -> None:
        """Subscribe an agent to receive messages."""
        if agent_id not in self._handlers:
            self._handlers[agent_id] = []
        self._handlers[agent_id].append(handler)
        logger.info(f"CollaborationService: {agent_id.value} subscribed")

    async def send_message(self, message: TaskMessage) -> str:
        """
        Send a structured message from one agent to another.

        Returns:
            The message_id.
        """
        self._message_log.append(message)
        logger.info(
            f"CollaborationService: {message.from_agent.value} → "
            f"{message.to_agent.value} [{message.message_type}]"
        )

        handlers = self._handlers.get(message.to_agent, [])
        for handler in handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(
                    f"CollaborationService: handler error for "
                    f"{message.to_agent.value}: {e}"
                )

        return message.message_id

    async def handoff_task(
        self,
        from_agent: AgentId,
        to_agent: AgentId,
        task_data: dict[str, Any],
        context: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> str:
        """
        Hand off a task from one agent to another with full context.

        Context preservation ensures the receiving agent has all
        necessary information to continue the workflow.
        """
        message = TaskMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="task_handoff",
            payload=task_data,
            context=context,
            correlation_id=correlation_id or str(uuid.uuid4()),
        )
        self._pending_handoffs[message.message_id] = message
        return await self.send_message(message)

    async def send_status_update(
        self,
        from_agent: AgentId,
        to_agent: AgentId,
        task_id: str,
        status: TaskStatus,
        details: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send a status update about a task."""
        message = TaskMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="status_update",
            payload={
                "task_id": task_id,
                "status": status.value,
                **(details or {}),
            },
            correlation_id=task_id,
        )
        return await self.send_message(message)

    async def send_result(
        self,
        from_agent: AgentId,
        to_agent: AgentId,
        task_id: str,
        result: dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> str:
        """Send task results from one agent to another."""
        message = TaskMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type="result",
            payload={"task_id": task_id, "result": result},
            correlation_id=correlation_id or task_id,
        )
        # Acknowledge handoff if pending
        self._pending_handoffs.pop(task_id, None)
        return await self.send_message(message)

    def get_message_log(
        self,
        agent_id: Optional[AgentId] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[TaskMessage]:
        """
        Get message history, optionally filtered.
        Useful for audit trails and debugging.
        """
        messages = self._message_log
        if agent_id:
            messages = [
                m for m in messages
                if m.from_agent == agent_id or m.to_agent == agent_id
            ]
        if correlation_id:
            messages = [
                m for m in messages if m.correlation_id == correlation_id
            ]
        return messages[-limit:]

    def get_pending_handoffs(self, agent_id: Optional[AgentId] = None) -> list[TaskMessage]:
        """Get pending task handoffs, optionally filtered by agent."""
        handoffs = list(self._pending_handoffs.values())
        if agent_id:
            handoffs = [h for h in handoffs if h.to_agent == agent_id]
        return handoffs
