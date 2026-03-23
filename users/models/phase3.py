import uuid

from sqlalchemy import (
    Column, Date, Integer, String, Boolean,
    DateTime, Text, ForeignKey, Index, Numeric,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base

USER_ID = "users.user_id"
ORGANIZATION_ID = "organization.id"


class UserGoal(Base):
    __tablename__ = "user_goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="active")  # active/completed/pending/cancelled
    due_date = Column(Date, nullable=True)
    progress_pct = Column(Integer, default=0)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    user = relationship("Users", foreign_keys=[user_id])


class UserActivity(Base):
    __tablename__ = "user_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    activity_type = Column(String(50), nullable=False)  # login/session/training/goal/assessment
    description = Column(String(500), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        Index("ix_user_activities_user_id_created_at", "user_id", "created_at"),
    )

    user = relationship("Users", foreign_keys=[user_id])


class CostRecord(Base):
    __tablename__ = "cost_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=True,
    )
    scope = Column(String(20), nullable=False)  # platform/company/team/user
    category = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        Index("ix_cost_records_scope_organization_id", "scope", "organization_id"),
    )

    organization = relationship("Organization", foreign_keys=[organization_id])
    user = relationship("Users", foreign_keys=[user_id])


class OrgNode(Base):
    __tablename__ = "org_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey(ORGANIZATION_ID, ondelete="CASCADE"),
        nullable=False,
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("org_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    name = Column(String(200), nullable=False)
    title = Column(String(200), nullable=True)
    node_type = Column(String(50), default="department")  # department/team/division
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="SET NULL"),
        nullable=True,
    )
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    organization = relationship("Organization", foreign_keys=[organization_id])
    parent = relationship("OrgNode", remote_side=[id], backref="children")
    user = relationship("Users", foreign_keys=[user_id])
