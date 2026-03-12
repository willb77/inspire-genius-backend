import enum
import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base


class IssueStatusEnum(enum.Enum):
    """Issue status options"""
    OPEN = "open"
    IN_PROGRESS = "in-progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IssuePriorityEnum(enum.Enum):
    """Issue priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueType(Base):
    """
    Model to represent different types of issues
    Examples: Technical Issue, Feature Request, Manager Update Request, Account Issue, Bug Report, Others
    """
    __tablename__ = "issue_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    issues = relationship("Issue", back_populates="issue_type")


class Issue(Base):
    """
    Model to represent user-reported issues related to agents
    """
    __tablename__ = "issues"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Issue details
    subject = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    issue_type_id = Column(UUID(as_uuid=True), ForeignKey("issue_types.id"), nullable=True)
    status = Column(
        String,
        nullable=False,
        default=IssueStatusEnum.OPEN.value
    )
    priority = Column(
        String,
        nullable=False,
        default=IssuePriorityEnum.MEDIUM.value
    )
    
    # Related entities
    reported_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to agent (may not be FK if agents are external)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True)
    business_id = Column(UUID(as_uuid=True), ForeignKey("business.id"), nullable=True)
    
    # Resolution tracking (simplified - no assignment workflow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_deleted = Column(Boolean, default=False)
    
    # Relationships
    reporter = relationship("Users", foreign_keys=[reported_by], back_populates="reported_issues")
    issue_type = relationship("IssueType", back_populates="issues")
    organization = relationship("Organization", foreign_keys=[organization_id])
    business = relationship("Business", foreign_keys=[business_id])
    comments = relationship("IssueComment", back_populates="issue", cascade="all, delete-orphan")
    attachments = relationship("IssueAttachment", back_populates="issue", cascade="all, delete-orphan")

    @property
    def is_open(self):
        """Check if issue is still open"""
        return self.status in [IssueStatusEnum.OPEN.value, IssueStatusEnum.IN_PROGRESS.value]

    @property
    def is_resolved(self):
        """Check if issue is resolved"""
        return self.status in [IssueStatusEnum.RESOLVED.value, IssueStatusEnum.CLOSED.value]
    
    @property
    def age_in_days(self):
        """Get age of issue in days"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return (now - self.created_at).days if self.created_at else 0


class IssueComment(Base):
    """
    Model to represent comments on issues
    """
    __tablename__ = "issue_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False)

    # Comment details
    comment = Column(Text, nullable=False)
    commented_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    is_admin_comment = Column(Boolean, default=False, nullable=False)

    # Audit fields
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_deleted = Column(Boolean, default=False)

    issue = relationship("Issue", back_populates="comments")
    commenter = relationship("Users", foreign_keys=[commented_by])


class IssueAttachment(Base):
    """
    Model to represent file attachments for issues
    """
    __tablename__ = "issue_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id = Column(UUID(as_uuid=True), ForeignKey("issues.id"), nullable=False)

    # File details
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_key = Column(String(500), nullable=False)  # S3 key
    file_type = Column(String(50), nullable=False)  # File extension
    file_size = Column(String(20), nullable=True)  # File size in bytes
    content_type = Column(String(100), nullable=True)  # MIME type

    # Uploader
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)

    # Audit fields
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_deleted = Column(Boolean, default=False)

    # Relationships
    issue = relationship("Issue", back_populates="attachments")
    uploader = relationship("Users", foreign_keys=[uploaded_by])
