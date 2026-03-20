from __future__ import annotations

"""Tests for CollaborationService — inter-agent messaging."""

import pytest
from unittest.mock import patch, AsyncMock

from ai.meridian.collaboration.collaboration_service import (
    CollaborationService,
    TaskMessage,
)
from ai.meridian.core.types import AgentId, TaskStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def collab() -> CollaborationService:
    return CollaborationService()


# ---------------------------------------------------------------------------
# subscribe + send_message
# ---------------------------------------------------------------------------

class TestSubscribeAndSend:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_subscribe_and_dispatch(self, mock_logger, collab):
        handler = AsyncMock()
        collab.subscribe(AgentId.ECHO, handler)

        msg = TaskMessage(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            message_type="request",
            payload={"data": 1},
        )
        msg_id = await collab.send_message(msg)

        assert msg_id == msg.message_id
        handler.assert_awaited_once_with(msg)

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_send_to_agent_with_no_subscribers(self, mock_logger, collab):
        """send_message should not raise even if no handler is registered."""
        msg = TaskMessage(
            from_agent=AgentId.AURA,
            to_agent=AgentId.FORGE,
            message_type="request",
        )
        msg_id = await collab.send_message(msg)
        assert isinstance(msg_id, str)

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_multiple_handlers(self, mock_logger, collab):
        h1 = AsyncMock()
        h2 = AsyncMock()
        collab.subscribe(AgentId.ECHO, h1)
        collab.subscribe(AgentId.ECHO, h2)

        msg = TaskMessage(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            message_type="request",
        )
        await collab.send_message(msg)

        h1.assert_awaited_once()
        h2.assert_awaited_once()


# ---------------------------------------------------------------------------
# handoff_task
# ---------------------------------------------------------------------------

class TestHandoffTask:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_handoff_creates_pending(self, mock_logger, collab):
        msg_id = await collab.handoff_task(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            task_data={"action": "assess"},
            context={"session": "s1"},
        )

        assert isinstance(msg_id, str)
        pending = collab.get_pending_handoffs()
        assert len(pending) == 1
        assert pending[0].message_type == "task_handoff"
        assert pending[0].to_agent == AgentId.ECHO

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_handoff_with_correlation_id(self, mock_logger, collab):
        await collab.handoff_task(
            from_agent=AgentId.NOVA,
            to_agent=AgentId.SENTINEL,
            task_data={},
            context={},
            correlation_id="corr_123",
        )

        pending = collab.get_pending_handoffs()
        assert pending[0].correlation_id == "corr_123"


# ---------------------------------------------------------------------------
# send_status_update
# ---------------------------------------------------------------------------

class TestSendStatusUpdate:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_status_update_message_type(self, mock_logger, collab):
        handler = AsyncMock()
        collab.subscribe(AgentId.MERIDIAN, handler)

        msg_id = await collab.send_status_update(
            from_agent=AgentId.ECHO,
            to_agent=AgentId.MERIDIAN,
            task_id="t1",
            status=TaskStatus.IN_PROGRESS,
            details={"progress": 50},
        )

        assert isinstance(msg_id, str)
        handler.assert_awaited_once()
        received_msg = handler.call_args[0][0]
        assert received_msg.message_type == "status_update"
        assert received_msg.payload["status"] == "in_progress"
        assert received_msg.payload["progress"] == 50
        assert received_msg.correlation_id == "t1"


# ---------------------------------------------------------------------------
# send_result
# ---------------------------------------------------------------------------

class TestSendResult:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_send_result_removes_pending_handoff(self, mock_logger, collab):
        # Create a handoff first
        msg_id = await collab.handoff_task(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            task_data={},
            context={},
        )

        # Pending should exist
        assert len(collab.get_pending_handoffs()) == 1

        # Send result referencing that handoff message_id as task_id
        await collab.send_result(
            from_agent=AgentId.ECHO,
            to_agent=AgentId.AURA,
            task_id=msg_id,
            result={"done": True},
        )

        # Pending handoff removed
        assert len(collab.get_pending_handoffs()) == 0

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_send_result_message_type(self, mock_logger, collab):
        handler = AsyncMock()
        collab.subscribe(AgentId.AURA, handler)

        await collab.send_result(
            from_agent=AgentId.ECHO,
            to_agent=AgentId.AURA,
            task_id="t2",
            result={"score": 0.85},
        )

        received = handler.call_args[0][0]
        assert received.message_type == "result"
        assert received.payload["result"]["score"] == 0.85


# ---------------------------------------------------------------------------
# get_message_log
# ---------------------------------------------------------------------------

class TestGetMessageLog:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_filter_by_agent_id(self, mock_logger, collab):
        await collab.send_message(TaskMessage(
            from_agent=AgentId.AURA, to_agent=AgentId.ECHO, message_type="request",
        ))
        await collab.send_message(TaskMessage(
            from_agent=AgentId.NOVA, to_agent=AgentId.SENTINEL, message_type="request",
        ))

        log = collab.get_message_log(agent_id=AgentId.AURA)
        assert len(log) == 1
        assert log[0].from_agent == AgentId.AURA

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_filter_by_correlation_id(self, mock_logger, collab):
        await collab.send_message(TaskMessage(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            message_type="request",
            correlation_id="corr_1",
        ))
        await collab.send_message(TaskMessage(
            from_agent=AgentId.AURA,
            to_agent=AgentId.ECHO,
            message_type="request",
            correlation_id="corr_2",
        ))

        log = collab.get_message_log(correlation_id="corr_1")
        assert len(log) == 1
        assert log[0].correlation_id == "corr_1"


# ---------------------------------------------------------------------------
# get_pending_handoffs
# ---------------------------------------------------------------------------

class TestGetPendingHandoffs:

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_filter_by_agent(self, mock_logger, collab):
        await collab.handoff_task(AgentId.AURA, AgentId.ECHO, {}, {})
        await collab.handoff_task(AgentId.AURA, AgentId.FORGE, {}, {})

        echo_handoffs = collab.get_pending_handoffs(agent_id=AgentId.ECHO)
        assert len(echo_handoffs) == 1
        assert echo_handoffs[0].to_agent == AgentId.ECHO

    @pytest.mark.asyncio
    @patch("ai.meridian.collaboration.collaboration_service.logger")
    async def test_all_pending(self, mock_logger, collab):
        await collab.handoff_task(AgentId.AURA, AgentId.ECHO, {}, {})
        await collab.handoff_task(AgentId.AURA, AgentId.FORGE, {}, {})

        assert len(collab.get_pending_handoffs()) == 2
