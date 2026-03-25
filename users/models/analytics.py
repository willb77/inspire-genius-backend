from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base

USER_ID = "users.user_id"


class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    report_type = Column(String(50), nullable=False)  # executive_summary/team_performance/cost_analysis
    title = Column(String(200), nullable=True)
    status = Column(String(20), default="pending")  # pending/generating/completed/failed
    format = Column(String(10), default="pdf")  # pdf/csv
    file_url = Column(String(500), nullable=True)
    file_key = Column(String(500), nullable=True)  # S3 key
    parameters_json = Column(Text, nullable=True)  # stored generation params
    error_message = Column(Text, nullable=True)
    scheduled_cron = Column(String(50), nullable=True)  # daily/weekly/monthly or null for one-off
    created_at = Column(DateTime(timezone=True), default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_reports_user_id", "user_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_created_at", "created_at"),
    )

    user = relationship("Users", foreign_keys=[user_id])


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(USER_ID, ondelete="CASCADE"),
        nullable=False,
    )
    scope = Column(String(20), nullable=False)  # user/team/company/platform
    format = Column(String(10), nullable=False)  # json/csv
    status = Column(String(20), default="pending")  # pending/processing/completed/failed
    progress_pct = Column(Integer, default=0)
    result_url = Column(String(500), nullable=True)
    result_key = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    total_records = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_export_jobs_user_id", "user_id"),
        Index("ix_export_jobs_status", "status"),
        Index("ix_export_jobs_created_at", "created_at"),
    )

    user = relationship("Users", foreign_keys=[user_id])
