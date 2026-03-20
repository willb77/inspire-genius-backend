from __future__ import annotations

"""
Meridian Memory Service — persistent memory with vector search.

Memory tiers:
- Short-term: session/conversation context (in-memory dict)
- Medium-term: user behavioral profiles, goals, preferences (Milvus + metadata)
- Long-term: organizational knowledge, Job Blueprints, PRISM libraries (Milvus)
- Feedback: human corrections as highest-priority entries (priority=10)
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import uuid


class MemoryTier(str, Enum):
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"
    FEEDBACK = "feedback"


class MemoryEntry(BaseModel):
    """A single memory entry stored in the system."""
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: MemoryTier
    agent_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=1, le=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class MemoryQueryResult(BaseModel):
    """Result from a memory query."""
    entries: list[MemoryEntry]
    total_count: int
    query: str


class MemoryService:
    """
    Persistent memory service for the Meridian agent system.

    Provides read/write access for all agents with:
    - Priority levels (human corrections = priority 10, highest)
    - Behavioral profile caching (PRISM data via Aura)
    - Tiered storage: short-term (session), medium-term (user), long-term (org)
    - Vector similarity search via Milvus for semantic recall
    """

    def __init__(self, milvus_client: Any = None) -> None:
        """
        Initialize the memory service.

        Args:
            milvus_client: Optional Milvus client instance. If None, uses the
                          singleton from prism_inspire.core.milvus_client.
        """
        self._milvus_client = milvus_client
        # Short-term memory is session-scoped, in-memory
        self._short_term: dict[str, list[MemoryEntry]] = {}
        # Cache for behavioral profiles (keyed by user_id)
        self._behavioral_cache: dict[str, dict[str, Any]] = {}

    def _get_milvus(self) -> Any:
        """Lazy-load Milvus client."""
        if self._milvus_client is None:
            from prism_inspire.core.milvus_client import milvus_client
            self._milvus_client = milvus_client
        return self._milvus_client

    async def store(self, entry: MemoryEntry) -> str:
        """
        Store a memory entry in the appropriate tier.

        Short-term entries are stored in-memory.
        Medium/long-term/feedback entries are persisted to Milvus.

        Returns:
            The entry_id of the stored memory.
        """
        entry.updated_at = datetime.utcnow()

        if entry.tier == MemoryTier.SHORT_TERM:
            session_key = entry.metadata.get("session_id", "default")
            if session_key not in self._short_term:
                self._short_term[session_key] = []
            self._short_term[session_key].append(entry)
            logger.debug(
                f"MemoryService: stored short-term memory {entry.entry_id} "
                f"for session {session_key}"
            )
        else:
            # Persist to Milvus for vector search
            try:
                store = self._get_milvus().get_store(
                    collection_name="meridian_memory"
                )
                store.add_texts(
                    texts=[entry.content],
                    metadatas=[{
                        "entry_id": entry.entry_id,
                        "tier": entry.tier.value,
                        "agent_id": entry.agent_id,
                        "user_id": entry.user_id or "",
                        "organization_id": entry.organization_id or "",
                        "priority": entry.priority,
                        "created_at": entry.created_at.isoformat(),
                    }],
                )
                logger.info(
                    f"MemoryService: persisted {entry.tier.value} memory "
                    f"{entry.entry_id} to Milvus"
                )
            except Exception as e:
                logger.error(f"MemoryService: failed to persist memory: {e}")
                raise

        return entry.entry_id

    async def recall(
        self,
        query: str,
        user_id: Optional[str] = None,
        tier: Optional[MemoryTier] = None,
        limit: int = 10,
    ) -> MemoryQueryResult:
        """
        Recall memories by semantic similarity search.

        Args:
            query: The search query for semantic matching.
            user_id: Optional filter by user.
            tier: Optional filter by memory tier.
            limit: Maximum number of results.

        Returns:
            MemoryQueryResult with matching entries.
        """
        entries: list[MemoryEntry] = []

        # Search short-term memory (exact text match for session context)
        if tier is None or tier == MemoryTier.SHORT_TERM:
            for session_entries in self._short_term.values():
                for entry in session_entries:
                    if user_id and entry.user_id != user_id:
                        continue
                    if query.lower() in entry.content.lower():
                        entries.append(entry)

        # Search Milvus for medium/long-term/feedback memories
        if tier is None or tier != MemoryTier.SHORT_TERM:
            try:
                store = self._get_milvus().get_store(
                    collection_name="meridian_memory"
                )
                results = store.similarity_search_with_score(
                    query=query,
                    k=limit,
                )
                for doc, score in results:
                    meta = doc.metadata
                    # Apply filters
                    if user_id and meta.get("user_id") != user_id:
                        continue
                    if tier and meta.get("tier") != tier.value:
                        continue
                    entries.append(MemoryEntry(
                        entry_id=meta.get("entry_id", str(uuid.uuid4())),
                        tier=MemoryTier(meta.get("tier", "medium_term")),
                        agent_id=meta.get("agent_id", "unknown"),
                        user_id=meta.get("user_id") or None,
                        organization_id=meta.get("organization_id") or None,
                        content=doc.page_content,
                        priority=meta.get("priority", 5),
                        metadata={"similarity_score": score},
                    ))
            except Exception as e:
                logger.error(f"MemoryService: Milvus recall failed: {e}")

        # Sort by priority (highest first), then by recency
        entries.sort(key=lambda e: (-e.priority, e.created_at), reverse=False)
        entries = entries[:limit]

        return MemoryQueryResult(
            entries=entries,
            total_count=len(entries),
            query=query,
        )

    async def store_feedback(
        self,
        agent_id: str,
        user_id: str,
        correction: str,
        original_output: str,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Store human correction as highest-priority feedback memory.

        Human corrections become high-priority memories that influence
        future agent behavior through RLHF-style feedback loops.
        """
        entry = MemoryEntry(
            tier=MemoryTier.FEEDBACK,
            agent_id=agent_id,
            user_id=user_id,
            content=f"CORRECTION: {correction}\nORIGINAL: {original_output}",
            priority=10,  # Highest priority
            metadata={
                "type": "human_correction",
                "original_output": original_output,
                "correction": correction,
                **(context or {}),
            },
        )
        return await self.store(entry)

    async def get_behavioral_profile(self, user_id: str) -> Optional[dict[str, Any]]:
        """
        Get cached behavioral profile (PRISM data) for a user.
        Falls back to Milvus search if not cached.
        """
        if user_id in self._behavioral_cache:
            return self._behavioral_cache[user_id]

        # Search for behavioral profile in medium-term memory
        results = await self.recall(
            query=f"PRISM behavioral profile for user",
            user_id=user_id,
            tier=MemoryTier.MEDIUM_TERM,
            limit=1,
        )
        if results.entries:
            profile = results.entries[0].metadata
            self._behavioral_cache[user_id] = profile
            return profile
        return None

    async def cache_behavioral_profile(
        self, user_id: str, profile: dict[str, Any]
    ) -> None:
        """Cache a user's behavioral profile from Aura."""
        self._behavioral_cache[user_id] = profile
        # Also persist to medium-term memory
        entry = MemoryEntry(
            tier=MemoryTier.MEDIUM_TERM,
            agent_id="aura",
            user_id=user_id,
            content=f"PRISM Behavioral Preference Map for user {user_id}",
            priority=8,
            metadata={"type": "behavioral_profile", "profile": profile},
        )
        await self.store(entry)

    def get_session_memories(self, session_id: str) -> list[MemoryEntry]:
        """Get all short-term memories for a session."""
        return self._short_term.get(session_id, [])

    def clear_session_memories(self, session_id: str) -> None:
        """Clear short-term memories for a session."""
        self._short_term.pop(session_id, None)
