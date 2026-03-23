from datetime import datetime, timedelta, timezone
import enum
import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from prism_inspire.db.base import Base


class SubscriptionTierEnum(enum.Enum):
    """Subscription tier options"""
    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class LicenseStatusEnum(enum.Enum):
    """License status options"""
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class License(Base):
    """
    Model to represent organization licenses and subscriptions
    """
    __tablename__ = "licenses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False)
    
    # Subscription details
    subscription_tier = Column(
        String,
        nullable=False,
        default=SubscriptionTierEnum.BASIC.value
    )
    status = Column(
        String,
        nullable=False,
        default=LicenseStatusEnum.ACTIVE.value
    )
    
    # License period
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now()
    )
    is_deleted = Column(Boolean, default=False)
    
    organization = relationship("Organization", back_populates="licenses")
    
    @property
    def is_active(self):
        """Check if license is currently active"""
        now = datetime.now(timezone.utc)
        start = self.start_date if self.start_date.tzinfo else self.start_date.replace(tzinfo=timezone.utc)
        end = self.end_date if self.end_date.tzinfo else self.end_date.replace(tzinfo=timezone.utc)

        return (
            self.status == LicenseStatusEnum.ACTIVE.value and
            start <= now <= end and
            not self.is_deleted
        )

    @property
    def is_expiring_soon(self, days=30):
        """Check if license is expiring within specified days"""
        now = datetime.now(timezone.utc)
        expiry_threshold = now + timedelta(days=days)
        end = self.end_date if self.end_date.tzinfo else self.end_date.replace(tzinfo=timezone.utc)
        
        return self.is_active and end <= expiry_threshold

    @property
    def days_until_expiry(self):
        """Get number of days until license expires"""
        now = datetime.now(timezone.utc)
        end = self.end_date if self.end_date.tzinfo else self.end_date.replace(tzinfo=timezone.utc)
        return max((end - now).days, 0)
