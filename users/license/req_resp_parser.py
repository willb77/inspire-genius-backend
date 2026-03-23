from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from users.models.license import SubscriptionTierEnum, LicenseStatusEnum


class CreateLicenseRequest(BaseModel):
    """Request model for creating a license"""
    organization_id: UUID = Field(..., description="Organization ID")
    subscription_tier: str = Field(..., description="Subscription tier")
    start_date: datetime = Field(..., description="License start date")
    end_date: datetime = Field(..., description="License end date")

    @field_validator('end_date')
    def validate_end_date(cls, v, info):
        start_date = info.data.get('start_date')
        if start_date and v <= start_date:
            raise ValueError('End date must be after start date')
        return v


class UpdateLicenseRequest(BaseModel):
    """Request model for updating a license"""
    subscription_tier: Optional[SubscriptionTierEnum] = Field(None, description="Subscription tier")
    status: Optional[LicenseStatusEnum] = Field(None, description="License status")
    start_date: Optional[datetime] = Field(None, description="License start date")
    end_date: Optional[datetime] = Field(None, description="License end date")

    @field_validator('end_date')
    def validate_end_date(cls, v, info):
        start_date = info.data.get('start_date')
        if start_date and v and v <= start_date:
            raise ValueError('End date must be after start date')
        return v
