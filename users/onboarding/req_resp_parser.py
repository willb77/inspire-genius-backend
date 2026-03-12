from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import date


class OnboardingProfileRequest(BaseModel):
    """Request model for user onboarding profile creation"""
    first_name: str = Field(..., min_length=1, max_length=50, description="User's first name")
    last_name: str = Field(..., min_length=1, max_length=50, description="User's last name")
    date_of_birth: Optional[date] = Field(None, description="User's date of birth")
    additional_info: Optional[str] = Field(None, max_length=500, description="Additional information about the user")

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate name fields are not empty after stripping"""
        if not v or not v.strip():
            raise ValueError("Name cannot be empty or whitespace")
        return v.strip()


class ProfileUpdateRequest(BaseModel):
    """Request model for updating user profile"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50, description="User's first name")
    last_name: Optional[str] = Field(None, min_length=1, max_length=50, description="User's last name")
    date_of_birth: Optional[date] = Field(None, description="User's date of birth")
    role_id: Optional[UUID] = Field(None, description="User's role ID")
    additional_info: Optional[str] = Field(None, max_length=500, description="Additional information about the user")

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate name fields are not empty after stripping if provided"""
        if v is not None:
            if not v.strip():
                raise ValueError("Name cannot be empty or whitespace")
            return v.strip()
        return v
