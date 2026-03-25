from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base

USER_ID = "users.user_id"
AGENT_ID = "agents.id"


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    response_id = Column(String(100), nullable=False)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey(AGENT_ID, ondelete="SET NULL"),
        nullable=True,
    )
    feedback_type = Column(String(20), nullable=False)  # thumbs_up/thumbs_down/correction/suggestion
    correction_text = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)  # 1-5
    context_json = Column(Text, nullable=True)  # stores conversation context
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_feedback_user_id", "user_id"),
        Index("ix_feedback_agent_id", "agent_id"),
        Index("ix_feedback_type", "feedback_type"),
        Index("ix_feedback_created_at", "created_at"),
    )

    user = relationship("Users", foreign_keys=[user_id])
    agent = relationship("Agent", foreign_keys=[agent_id])
    corrections = relationship("FeedbackCorrection", back_populates="feedback", cascade="all, delete-orphan")


class FeedbackCorrection(Base):
    __tablename__ = "feedback_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id = Column(
        UUID(as_uuid=True),
        ForeignKey("feedback.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_response = Column(Text, nullable=True)
    corrected_response = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending/approved/rejected/applied
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    weight = Column(Float, default=1.0)  # correction priority weight
    applied_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_feedback_corrections_feedback_id", "feedback_id"),
        Index("ix_feedback_corrections_status", "status"),
    )

    feedback = relationship("Feedback", back_populates="corrections")
    reviewer = relationship("Users", foreign_keys=[reviewed_by])


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey(AGENT_ID, ondelete="SET NULL"),
        nullable=True,
    )
    template_text = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), default="draft")  # draft/active/archived
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    variables_json = Column(Text, nullable=True)  # list of {{var}} placeholders
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="SET NULL"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
        Index("ix_prompt_templates_agent_id", "agent_id"),
        Index("ix_prompt_templates_status", "status"),
    )

    agent = relationship("Agent", foreign_keys=[agent_id])
    parent = relationship("PromptTemplate", remote_side=[id])
    creator = relationship("Users", foreign_keys=[created_by])


class AgentMemory(Base):
    __tablename__ = "agent_memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey(AGENT_ID, ondelete="CASCADE"),
        nullable=False,
    )
    memory_type = Column(String(30), nullable=False)  # correction/training/context
    content = Column(Text, nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)  # FK to feedback_corrections.id if type=correction
    weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_agent_memories_agent_id", "agent_id"),
        Index("ix_agent_memories_memory_type", "memory_type"),
        Index("ix_agent_memories_is_active", "is_active"),
    )

    agent = relationship("Agent", foreign_keys=[agent_id])
