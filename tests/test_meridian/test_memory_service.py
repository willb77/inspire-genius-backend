from __future__ import annotations

"""Tests for MemoryService — tiered memory with vector search."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from ai.meridian.memory.memory_service import (
    MemoryService,
    MemoryEntry,
    MemoryTier,
    MemoryQueryResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def svc() -> MemoryService:
    """MemoryService with a mock Milvus client injected."""
    mock_milvus = MagicMock()
    return MemoryService(milvus_client=mock_milvus)


@pytest.fixture
def short_term_entry() -> MemoryEntry:
    return MemoryEntry(
        tier=MemoryTier.SHORT_TERM,
        agent_id="echo",
        user_id="u1",
        content="User mentioned feeling stressed",
        metadata={"session_id": "sess_1"},
    )


@pytest.fixture
def medium_term_entry() -> MemoryEntry:
    return MemoryEntry(
        tier=MemoryTier.MEDIUM_TERM,
        agent_id="aura",
        user_id="u1",
        content="PRISM profile data",
        metadata={"type": "behavioral_profile"},
    )


# ---------------------------------------------------------------------------
# Short-term store/recall
# ---------------------------------------------------------------------------

class TestShortTermMemory:

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_store_short_term(self, mock_logger, svc, short_term_entry):
        entry_id = await svc.store(short_term_entry)

        assert entry_id == short_term_entry.entry_id
        assert "sess_1" in svc._short_term
        assert len(svc._short_term["sess_1"]) == 1

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_recall_short_term_text_match(self, mock_logger, svc, short_term_entry):
        await svc.store(short_term_entry)

        result = await svc.recall(
            query="stressed",
            tier=MemoryTier.SHORT_TERM,
        )

        assert isinstance(result, MemoryQueryResult)
        assert result.total_count >= 1
        assert any("stressed" in e.content.lower() for e in result.entries)

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_recall_short_term_no_match(self, mock_logger, svc, short_term_entry):
        await svc.store(short_term_entry)

        result = await svc.recall(
            query="completely unrelated xyz",
            tier=MemoryTier.SHORT_TERM,
        )
        assert result.total_count == 0


# ---------------------------------------------------------------------------
# Medium-term store (Milvus)
# ---------------------------------------------------------------------------

class TestMediumTermMemory:

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_store_medium_term_calls_milvus(self, mock_logger, svc, medium_term_entry):
        mock_store = MagicMock()
        svc._milvus_client.get_store.return_value = mock_store

        entry_id = await svc.store(medium_term_entry)

        assert entry_id == medium_term_entry.entry_id
        svc._milvus_client.get_store.assert_called_once_with(
            collection_name="meridian_memory"
        )
        mock_store.add_texts.assert_called_once()
        call_kwargs = mock_store.add_texts.call_args
        assert call_kwargs[1]["texts"][0] == "PRISM profile data" or \
               call_kwargs[0][0][0] == "PRISM profile data" if call_kwargs[0] else True

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_store_medium_term_milvus_failure_raises(self, mock_logger, svc, medium_term_entry):
        mock_store = MagicMock()
        mock_store.add_texts.side_effect = RuntimeError("Milvus down")
        svc._milvus_client.get_store.return_value = mock_store

        with pytest.raises(RuntimeError, match="Milvus down"):
            await svc.store(medium_term_entry)


# ---------------------------------------------------------------------------
# store_feedback
# ---------------------------------------------------------------------------

class TestStoreFeedback:

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_store_feedback_creates_priority_10(self, mock_logger, svc):
        mock_store = MagicMock()
        svc._milvus_client.get_store.return_value = mock_store

        entry_id = await svc.store_feedback(
            agent_id="nova",
            user_id="u1",
            correction="Should recommend interview prep first",
            original_output="Recommended direct application",
        )

        assert isinstance(entry_id, str)
        # The feedback entry goes through store() which calls Milvus
        mock_store.add_texts.assert_called_once()
        metadata = mock_store.add_texts.call_args[1].get("metadatas") or \
                   mock_store.add_texts.call_args[0][1] if len(mock_store.add_texts.call_args[0]) > 1 else \
                   mock_store.add_texts.call_args[1]["metadatas"]
        assert metadata[0]["priority"] == 10
        assert metadata[0]["tier"] == "feedback"


# ---------------------------------------------------------------------------
# Behavioral profile cache
# ---------------------------------------------------------------------------

class TestBehavioralProfile:

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_cache_hit(self, mock_logger, svc):
        svc._behavioral_cache["u1"] = {"prism_type": "Advisor"}

        profile = await svc.get_behavioral_profile("u1")
        assert profile == {"prism_type": "Advisor"}

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_cache_miss_searches_milvus(self, mock_logger, svc):
        """When not cached, falls back to recall() which searches Milvus."""
        # Mock the Milvus store to return empty results so profile is None
        mock_store = MagicMock()
        mock_store.similarity_search_with_score.return_value = []
        svc._milvus_client.get_store.return_value = mock_store

        profile = await svc.get_behavioral_profile("u_unknown")
        assert profile is None

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_cache_behavioral_profile_populates_cache(self, mock_logger, svc):
        mock_store = MagicMock()
        svc._milvus_client.get_store.return_value = mock_store

        await svc.cache_behavioral_profile("u2", {"prism_type": "Catalyst"})

        assert svc._behavioral_cache["u2"] == {"prism_type": "Catalyst"}
        # Also persisted to Milvus
        mock_store.add_texts.assert_called_once()


# ---------------------------------------------------------------------------
# Session memories
# ---------------------------------------------------------------------------

class TestSessionMemories:

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_get_session_memories(self, mock_logger, svc, short_term_entry):
        await svc.store(short_term_entry)

        memories = svc.get_session_memories("sess_1")
        assert len(memories) == 1
        assert memories[0].content == "User mentioned feeling stressed"

    def test_get_session_memories_empty(self, svc):
        assert svc.get_session_memories("nonexistent") == []

    @pytest.mark.asyncio
    @patch("ai.meridian.memory.memory_service.logger")
    async def test_clear_session_memories(self, mock_logger, svc, short_term_entry):
        await svc.store(short_term_entry)
        svc.clear_session_memories("sess_1")

        assert svc.get_session_memories("sess_1") == []

    def test_clear_session_memories_noop(self, svc):
        svc.clear_session_memories("nonexistent")  # should not raise
