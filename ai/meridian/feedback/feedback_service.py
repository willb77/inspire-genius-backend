from __future__ import annotations

"""
RLHF Feedback Pipeline — processes corrections, tracks outcomes, exports training data.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import uuid


class FeedbackEntry(BaseModel):
    """A single feedback entry in the RLHF pipeline."""
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    session_id: str
    agent_id: str
    original_response: str
    correction: Optional[str] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    outcome: Optional[str] = None  # "helpful", "not_helpful", "harmful"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackStats(BaseModel):
    """Aggregated feedback statistics."""
    total_feedback: int = 0
    total_corrections: int = 0
    avg_rating: Optional[float] = None
    outcome_distribution: dict[str, int] = Field(default_factory=dict)
    by_agent: dict[str, dict[str, Any]] = Field(default_factory=dict)


class FeedbackService:
    """
    RLHF Feedback Pipeline.

    Full loop: user rates -> correction stored as priority-10 memory ->
    periodic export for fine-tuning -> prompt iteration via Prompt Builder.
    """

    def __init__(self, memory_service: Any = None) -> None:
        self._memory_service = memory_service
        self._entries: list[FeedbackEntry] = []

    async def record_feedback(
        self,
        user_id: str,
        session_id: str,
        agent_id: str,
        original_response: str,
        correction: Optional[str] = None,
        rating: Optional[int] = None,
        outcome: Optional[str] = None,
    ) -> str:
        """Record user feedback and store correction as high-priority memory."""
        entry = FeedbackEntry(
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            original_response=original_response,
            correction=correction,
            rating=rating,
            outcome=outcome,
        )
        self._entries.append(entry)

        # Store correction as high-priority memory
        if correction and self._memory_service:
            await self._memory_service.store_feedback(
                agent_id=agent_id,
                user_id=user_id,
                correction=correction,
                original_output=original_response,
                context={
                    "session_id": session_id,
                    "rating": rating,
                    "outcome": outcome,
                    "feedback_id": entry.feedback_id,
                },
            )
            logger.info(
                f"FeedbackService: correction stored for agent {agent_id}, "
                f"feedback_id={entry.feedback_id}"
            )

        return entry.feedback_id

    async def record_decision_outcome(
        self,
        feedback_id: str,
        outcome: str,
        details: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Update a feedback entry with the decision outcome."""
        for entry in self._entries:
            if entry.feedback_id == feedback_id:
                entry.outcome = outcome
                if details:
                    entry.metadata.update(details)
                return True
        return False

    def get_stats(self, agent_id: Optional[str] = None) -> FeedbackStats:
        """Get aggregated feedback statistics."""
        entries = self._entries
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]

        ratings = [e.rating for e in entries if e.rating is not None]
        corrections = [e for e in entries if e.correction]
        outcomes: dict[str, int] = {}
        for e in entries:
            if e.outcome:
                outcomes[e.outcome] = outcomes.get(e.outcome, 0) + 1

        # Per-agent breakdown
        by_agent: dict[str, dict[str, Any]] = {}
        for e in entries:
            if e.agent_id not in by_agent:
                by_agent[e.agent_id] = {"count": 0, "corrections": 0, "ratings": []}
            by_agent[e.agent_id]["count"] += 1
            if e.correction:
                by_agent[e.agent_id]["corrections"] += 1
            if e.rating is not None:
                by_agent[e.agent_id]["ratings"].append(e.rating)

        for aid, data in by_agent.items():
            r = data.pop("ratings")
            data["avg_rating"] = sum(r) / len(r) if r else None

        return FeedbackStats(
            total_feedback=len(entries),
            total_corrections=len(corrections),
            avg_rating=sum(ratings) / len(ratings) if ratings else None,
            outcome_distribution=outcomes,
            by_agent=by_agent,
        )

    def export_training_data(self, min_rating: Optional[int] = None) -> list[dict[str, Any]]:
        """
        Export feedback as training data for fine-tuning.

        Returns list of {original, correction, rating, agent_id} dicts.
        Only includes entries with corrections.
        """
        data = []
        for entry in self._entries:
            if not entry.correction:
                continue
            if min_rating and entry.rating and entry.rating < min_rating:
                continue
            data.append({
                "original": entry.original_response,
                "correction": entry.correction,
                "rating": entry.rating,
                "agent_id": entry.agent_id,
                "user_id": entry.user_id,
                "outcome": entry.outcome,
                "created_at": entry.created_at.isoformat(),
            })
        return data

    def get_entry_count(self) -> int:
        return len(self._entries)
