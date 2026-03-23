from pydantic import BaseModel, Field, EmailStr
from enum import Enum
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from users.models.user import BusinessTypeEnum, InvitationStatusEnum, OrganizationTypeEnum


class SingleAgentPreferenceForOrganization(BaseModel):
    """Single agent preference for organization assignment"""
    agent_id: UUID = Field(..., description="Agent ID")
    tone_ids: List[UUID] = Field(..., description="List of Tone IDs (can select multiple)")
    accent_id: UUID = Field(..., description="Accent ID")
    gender_id: UUID = Field(..., description="Gender ID")


class BusinessCreateRequest(BaseModel):
    """Request model for creating a business"""
    name: str = Field(
        ...,
        description="Business name",
        min_length=2,
        max_length=150
    )
    description: Optional[str] = Field(
        None,
        description="Business description",
        max_length=1000
    )
    contact_email: Optional[EmailStr] = Field(
        None,
        description="Business contact email"
    )
    contact_phone: Optional[str] = Field(
        None,
        description="Business contact phone",
        max_length=15
    )
    business_type: BusinessTypeEnum = Field(
        BusinessTypeEnum.CORPORATE,
        description="Type of business"
    )

# Agent Management Schemas
class AgentResponse(BaseModel):
    """Response model for agent"""
    id: UUID
    name: str
    category_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrganizationAgentResponse(BaseModel):
    """Response model for organization agent assignment"""
    id: UUID
    organization_id: UUID
    agent_id: UUID
    assigned_by: Optional[UUID] = None
    assigned_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# Agent-Organization Management Schemas
class AgentOrganizationAssignRequest(BaseModel):
    """Request model for assigning agents to an organization with preferences"""
    preferences: List[SingleAgentPreferenceForOrganization] = Field(..., description="List of agent preferences")


class AgentOrganizationRemoveRequest(BaseModel):
    """Request model for removing an agent from an organization"""
    agent_ids: List[str]


class AgentBusinessAssignRequest(BaseModel):
    """Request model for giving business access to agents (uses organization settings)"""
    agent_ids: List[UUID] = Field(..., description="List of agent IDs from organization to give business access to")


class AgentBusinessRemoveRequest(BaseModel):
    """Request model for removing agent access from a business"""
    agent_ids: List[UUID] = Field(..., description="List of agent IDs to remove")


class OrganizationUpdateRequest(BaseModel):
    """Request model for updating an organization"""
    name: Optional[str] = Field(
        None,
        description="Organization name",
        min_length=2,
        max_length=150
    )
    contact: Optional[str] = Field(
        None,
        description="Contact phone number",
        min_length=10,
        max_length=15
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Organization email"
    )
    address: Optional[str] = Field(
        None,
        description="Organization address",
        max_length=500
    )
    website_url: Optional[str] = Field(
        None,
        description="Website URL",
        max_length=255
    )


class BusinessUpdateRequest(BaseModel):
    """Request model for updating a business (name only)"""
    name: str = Field(
        ...,
        description="Business name",
        min_length=2,
        max_length=150
    )
