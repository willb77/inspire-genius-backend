from __future__ import annotations

"""
Agent Analytics Dashboard — tracks per-agent usage, satisfaction, and handoff metrics.
"""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger
import uuid


class AgentUsageRecord(BaseModel):
    """A single agent usage event."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    action: str
    user_id: str
    session_id: str
    confidence: float = 0.0
    status: str = "completed"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    rating: Optional[int] = None  # 1-5 user satisfaction


class AgentMetrics(BaseModel):
    """Aggregated metrics for a single agent."""
    agent_id: str
    total_invocations: int = 0
    successful: int = 0
    failed: int = 0
    avg_confidence: float = 0.0
    avg_rating: Optional[float] = None
    action_breakdown: dict[str, int] = Field(default_factory=dict)
    prism_profile_distribution: dict[str, int] = Field(default_factory=dict)


class AgentAnalytics:
    """
    Tracks per-agent usage, satisfaction, and behavioral correlations.
    Provides data for super-admin dashboard views.
    """

    def __init__(self) -> None:
        self._records: list[AgentUsageRecord] = []

    def record_usage(
        self,
        agent_id: str,
        action: str,
        user_id: str,
        session_id: str,
        confidence: float = 0.0,
        status: str = "completed",
        rating: Optional[int] = None,
        prism_primary: Optional[str] = None,
    ) -> str:
        """Record an agent usage event. Returns the record_id."""
        record = AgentUsageRecord(
            agent_id=agent_id,
            action=action,
            user_id=user_id,
            session_id=session_id,
            confidence=confidence,
            status=status,
            rating=rating,
        )
        self._records.append(record)

        # Track PRISM correlation if available
        if prism_primary:
            record_data = record.model_dump()
            record_data["prism_primary"] = prism_primary
            # Store back as metadata (for metrics computation)

        logger.debug(f"Analytics: recorded {agent_id}.{action} for user {user_id}")
        return record.record_id

    def get_agent_metrics(self, agent_id: Optional[str] = None) -> list[AgentMetrics]:
        """Get aggregated metrics, optionally filtered by agent."""
        # Group records by agent
        by_agent: dict[str, list[AgentUsageRecord]] = {}
        for r in self._records:
            if agent_id and r.agent_id != agent_id:
                continue
            if r.agent_id not in by_agent:
                by_agent[r.agent_id] = []
            by_agent[r.agent_id].append(r)

        metrics = []
        for aid, records in by_agent.items():
            successful = sum(1 for r in records if r.status == "completed")
            failed = sum(1 for r in records if r.status == "failed")
            confidences = [r.confidence for r in records if r.confidence > 0]
            ratings = [r.rating for r in records if r.rating is not None]

            action_counts: dict[str, int] = {}
            for r in records:
                action_counts[r.action] = action_counts.get(r.action, 0) + 1

            metrics.append(AgentMetrics(
                agent_id=aid,
                total_invocations=len(records),
                successful=successful,
                failed=failed,
                avg_confidence=sum(confidences) / len(confidences) if confidences else 0.0,
                avg_rating=sum(ratings) / len(ratings) if ratings else None,
                action_breakdown=action_counts,
            ))

        return metrics

    def get_dashboard_summary(self) -> dict[str, Any]:
        """Get a summary suitable for the super-admin dashboard."""
        all_metrics = self.get_agent_metrics()
        total = sum(m.total_invocations for m in all_metrics)
        total_success = sum(m.successful for m in all_metrics)

        return {
            "total_invocations": total,
            "total_successful": total_success,
            "success_rate": total_success / total if total > 0 else 0.0,
            "active_agents": len(all_metrics),
            "agents": [m.model_dump() for m in all_metrics],
        }

    def get_record_count(self) -> int:
        """Get total number of usage records."""
        return len(self._records)
