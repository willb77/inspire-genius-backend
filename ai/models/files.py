from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from prism_inspire.db.base import Base


class File(Base):
    __tablename__ = "files"
    id = Column(UUID(as_uuid=True), primary_key=True)
    hash = Column(String(64), nullable=True)
    filename = Column(String(255), nullable=False)
    s3url = Column(String(1024), nullable=True)
    file_uuid = Column(UUID(as_uuid=True), unique=True, nullable=True)
    file_type = Column(String(50), nullable=False)
    file_key = Column(String(255), nullable=True)
    exception = Column(String(1024), nullable=True)
    converted_file_key = Column(String(255), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime,
        default=func.now(),
        server_onupdate=func.now(),
        onupdate=func.now(),
    )
    is_deleted = Column(Boolean, default=False)

    category = relationship("Category", back_populates="files")
    user = relationship("Users", back_populates="files")
    reports = relationship("Report", back_populates="file")


class Report(Base):
    __tablename__ = "reports"
    id = Column(UUID(as_uuid=True), primary_key=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True)
    report_str = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    file = relationship("File", back_populates="reports")
