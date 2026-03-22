import enum
import uuid

from sqlalchemy import (
    Column, Date, Integer, String, Boolean,
    DateTime, Float, Text, Enum, ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base

USER_ID = "users.user_id"


class TrainingStatusEnum(enum.Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class HiringPositionStatusEnum(enum.Enum):
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
    __tablename__ = "training_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
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
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    manager = relationship("Users", foreign_keys=[manager_id])
    user = relationship("Users", foreign_keys=[user_id])


class HiringPosition(Base):
    __tablename__ = "hiring_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        nullable=True,
    )
    title = Column(String(200), nullable=False)
    department = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(HiringPositionStatusEnum, name="hiring_position_status_enum"),
        nullable=False,
        default=HiringPositionStatusEnum.OPEN,
    )
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    manager = relationship("Users", foreign_keys=[manager_id])
    organization = relationship("Organization")
    candidates = relationship(
        "Candidate",
        back_populates="position",
        cascade="all, delete-orphan",
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hiring_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
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
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    position = relationship("HiringPosition", back_populates="candidates")
    interviews = relationship(
        "Interview",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class Interview(Base):
    __tablename__ = "interviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    interviewer_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
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
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    candidate = relationship("Candidate", back_populates="interviews")
    interviewer = relationship("Users", foreign_keys=[interviewer_id])
