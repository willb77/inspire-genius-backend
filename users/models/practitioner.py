"""
Practitioner domain models — clients, coaching sessions, credits, follow-ups.
"""
import enum
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Integer, Text,
    func, ForeignKey, Enum, Float, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from prism_inspire.db.base import Base

USER_ID = "users.user_id"


class SessionStatusEnum(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class FollowUpPriorityEnum(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class FollowUpStatusEnum(enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PractitionerClient(Base):
    """A client relationship between a practitioner and a user."""
    __tablename__ = "practitioner_clients"

    id = Column(UUID(as_uuid=True), primary_key=True)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    prism_score = Column(Float, nullable=True)
    session_count = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, paused, completed
    notes = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    practitioner = relationship("Users", foreign_keys=[practitioner_id])
    client = relationship("Users", foreign_keys=[client_id])
    sessions = relationship("CoachingSession", back_populates="client_rel", cascade="all, delete-orphan")


class CoachingSession(Base):
    """A coaching session between practitioner and client."""
    __tablename__ = "coaching_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    practitioner_client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("practitioner_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=60)
    status = Column(
        Enum(SessionStatusEnum, name="coaching_session_status_enum"),
        nullable=False,
        default=SessionStatusEnum.SCHEDULED,
    )
    session_type = Column(String(50), default="one_on_one")  # one_on_one, group, assessment
    notes = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    credits_used = Column(Numeric(10, 2), default=1)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    client_rel = relationship("PractitionerClient", back_populates="sessions")
    practitioner = relationship("Users", foreign_keys=[practitioner_id])
    client = relationship("Users", foreign_keys=[client_id])


class PractitionerCredit(Base):
    """Credit ledger for a practitioner — tracks balance, usage, and purchases."""
    __tablename__ = "practitioner_credits"

    id = Column(UUID(as_uuid=True), primary_key=True)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False, unique=True)
    total_credits = Column(Numeric(10, 2), default=0)
    used_credits = Column(Numeric(10, 2), default=0)
    reserved_credits = Column(Numeric(10, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    practitioner = relationship("Users", foreign_keys=[practitioner_id])

    @property
    def available_credits(self):
        return self.total_credits - self.used_credits - self.reserved_credits


class FollowUp(Base):
    """A follow-up task for a practitioner regarding a client."""
    __tablename__ = "follow_ups"

    id = Column(UUID(as_uuid=True), primary_key=True)
    practitioner_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=False)
    priority = Column(
        Enum(FollowUpPriorityEnum, name="follow_up_priority_enum"),
        nullable=False,
        default=FollowUpPriorityEnum.MEDIUM,
    )
    status = Column(
        Enum(FollowUpStatusEnum, name="follow_up_status_enum"),
        nullable=False,
        default=FollowUpStatusEnum.PENDING,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    practitioner = relationship("Users", foreign_keys=[practitioner_id])
    client = relationship("Users", foreign_keys=[client_id])
