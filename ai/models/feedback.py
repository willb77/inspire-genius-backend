"""
Feedback data models for persistent storage of user feedback, corrections,
and training data exports.
"""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from prism_inspire.db.base import Base


# ── Enums ─────────────────────────────────────────────────────────────

class FeedbackTypeEnum(enum.Enum):
    correction = "correction"
    rating = "rating"
    thumbs_up = "thumbs_up"
    thumbs_down = "thumbs_down"
    comment = "comment"


class ExportFormatEnum(enum.Enum):
    jsonl = "jsonl"
    csv = "csv"
    parquet = "parquet"


class ExportStatusEnum(enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ── Models ────────────────────────────────────────────────────────────

class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True)
    original_response = Column(Text, nullable=False)
    correction = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5
    feedback_type = Column(
        Enum(FeedbackTypeEnum, name="feedback_type_enum"),
        nullable=False,
        default=FeedbackTypeEnum.rating,
    )
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    corrections = relationship("FeedbackCorrection", back_populates="feedback", lazy="selectin")

    __table_args__ = (
        Index("ix_feedback_user_created", "user_id", "created_at"),
        Index("ix_feedback_agent_rating", "agent_id", "rating"),
        Index("ix_feedback_created_at", "created_at"),
        Index("ix_feedback_type", "feedback_type"),
    )


class FeedbackCorrection(Base):
    __tablename__ = "feedback_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id = Column(
        UUID(as_uuid=True), ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False
    )
    field_name = Column(String(255), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    applied = Column(Boolean, default=False, nullable=False)
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    feedback = relationship("Feedback", back_populates="corrections")

    __table_args__ = (
        Index("ix_feedback_corrections_feedback_id", "feedback_id"),
    )


class TrainingExport(Base):
    __tablename__ = "training_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    export_format = Column(
        Enum(ExportFormatEnum, name="export_format_enum"),
        nullable=False,
        default=ExportFormatEnum.jsonl,
    )
    filters = Column(JSONB, nullable=True, default=dict)  # date range, agent, rating filters
    record_count = Column(Integer, nullable=True)
    file_url = Column(String(1024), nullable=True)  # S3 path
    status = Column(
        Enum(ExportStatusEnum, name="export_status_enum"),
        nullable=False,
        default=ExportStatusEnum.pending,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_training_exports_status", "status"),
        Index("ix_training_exports_created_by", "created_by"),
    )
