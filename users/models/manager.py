"""
Manager domain models — team management, training, hiring pipeline.
"""
import enum
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Integer, Text,
    func, ForeignKey, Enum, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from prism_inspire.db.base import Base

USER_ID = "users.user_id"
PROFILE_ID = "user_profiles.id"


class TrainingStatusEnum(enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PositionStatusEnum(enum.Enum):
    OPEN = "open"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    FILLED = "filled"
    CLOSED = "closed"


class CandidateStatusEnum(enum.Enum):
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEWING = "interviewing"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class InterviewStatusEnum(enum.Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class TrainingAssignment(Base):
    """A training course or module assigned by a manager to a team member."""
    __tablename__ = "training_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(
        Enum(TrainingStatusEnum, name="training_status_enum"),
        nullable=False,
        default=TrainingStatusEnum.ASSIGNED,
    )
    progress_pct = Column(Integer, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    manager = relationship("Users", foreign_keys=[manager_id])
    user = relationship("Users", foreign_keys=[user_id])


class HiringPosition(Base):
    """An open position managed by a manager for hiring."""
    __tablename__ = "hiring_positions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True)
    title = Column(String(200), nullable=False)
    department = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(PositionStatusEnum, name="position_status_enum"),
        nullable=False,
        default=PositionStatusEnum.OPEN,
    )
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    manager = relationship("Users", foreign_keys=[manager_id])
    organization = relationship("Organization")
    candidates = relationship("Candidate", back_populates="position", cascade="all, delete-orphan")


class Candidate(Base):
    """A candidate in the hiring pipeline for a position."""
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True)
    position_id = Column(UUID(as_uuid=True), ForeignKey("hiring_positions.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=True)
    phone = Column(String(30), nullable=True)
    resume_url = Column(String(500), nullable=True)
    status = Column(
        Enum(CandidateStatusEnum, name="candidate_status_enum"),
        nullable=False,
        default=CandidateStatusEnum.APPLIED,
    )
    prism_score = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    position = relationship("HiringPosition", back_populates="candidates")
    interviews = relationship("Interview", back_populates="candidate", cascade="all, delete-orphan")


class Interview(Base):
    """A scheduled interview between a manager and a candidate."""
    __tablename__ = "interviews"

    id = Column(UUID(as_uuid=True), primary_key=True)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    interviewer_id = Column(UUID(as_uuid=True), ForeignKey(USER_ID), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=30)
    location = Column(String(200), nullable=True)
    meeting_url = Column(String(500), nullable=True)
    status = Column(
        Enum(InterviewStatusEnum, name="interview_status_enum"),
        nullable=False,
        default=InterviewStatusEnum.SCHEDULED,
    )
    notes = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    candidate = relationship("Candidate", back_populates="interviews")
    interviewer = relationship("Users", foreign_keys=[interviewer_id])
