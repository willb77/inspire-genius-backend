from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Constants
CATEGORY_NAME_DESCRIPTION = "Category name"


class SingleAgentPreference(BaseModel):
    agent_id: UUID = Field(..., description="Agent ID")
    tone_ids: List[UUID] = Field(..., description="List of Tone IDs (can select multiple)")
    accent_id: UUID = Field(..., description="Accent ID")
    gender_id: UUID = Field(..., description="Gender ID")


class AgentPreferenceRequest(BaseModel):
    preferences: List[SingleAgentPreference]


class UpdateAgentPreference(BaseModel):
    tone_ids: List[UUID] = Field(..., description="List of Tone IDs (can select multiple)")
    accent_id: UUID = Field(..., description="Accent ID")
    gender_id: UUID = Field(..., description="Gender ID")


class CreateAgentRequest(BaseModel):
    name: str = Field(..., description="Agent name")
    category_name: str = Field(..., description=CATEGORY_NAME_DESCRIPTION)
    prompt: str = Field(..., description="Prompt text")


class UpdateAgentRequest(BaseModel):
    name: Optional[str] = Field(None, description="Agent name")
    category_name: Optional[str] = Field(None, description=CATEGORY_NAME_DESCRIPTION)
    prompt: Optional[str] = Field(None, description="Prompt text")
    status: Optional[str] = Field(None, description="status")


class CreateCategoryRequest(BaseModel):
    name: str = Field(..., description=CATEGORY_NAME_DESCRIPTION)
    display_name: Optional[str] = Field(None, description="Display name")
    type: Literal["file", "agent", "both"] = Field("both", description="Category type")


class AssignAgentsToUserRequest(BaseModel):
    """
    Request model for assigning or removing agents for a user.
    Super admin can:
    - Assign custom agents to users (is_active=True)
    - Remove/block predefined agents from users (is_active=False)
    """
    user_id: UUID = Field(..., description="User ID to assign agents to")
    agent_ids: List[UUID] = Field(..., description="List of agent IDs to assign or remove")
    is_active: bool = Field(True, description="True to assign agents, False to remove/block agents")


class GetUserAssignedAgentsResponse(BaseModel):
    """Response model for getting user's agent assignments"""
    assigned_agent_ids: List[str] = Field(..., description="Custom agents explicitly assigned to user")
    removed_agent_ids: List[str] = Field(..., description="Predefined agents explicitly removed from user")
