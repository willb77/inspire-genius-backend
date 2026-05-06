"""Task result ORM (Combined Plan A.E3.4 — Save to Workspace).

Persists structured task-agent results so users can revisit them without
re-running the prompt. Created via the migration-runner Lambda on
2026-05-06 (Transformation Documents/004_e3_task_results.sql).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from prism_inspire.db.base import Base


class TaskResult(Base):
    __tablename__ = "task_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    org_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    task_slug = Column(String(64), nullable=False, index=True)
    agent_id = Column(String(64), nullable=False)
    request_payload = Column(JSONB, nullable=False)
    result_payload = Column(JSONB, nullable=False)
    confidence = Column(Float, nullable=True)
    title = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
