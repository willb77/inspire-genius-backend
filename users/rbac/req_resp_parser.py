from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
from uuid import UUID


class RoleRequest(BaseModel):
    """
    Request model for creating a role
    """
    name: str = Field(
        ...,
        description="Role name",
        min_length=2, max_length=50
    )


class RoleUpdateRequest(BaseModel):
    """
    Request model for updating a role
    """
    name: str = Field(
        ...,
        description="Role name",
        min_length=2, max_length=50
    )


class GroupRequest(BaseModel):
    """
    Request model for creating a group
    """
    name: str = Field(
        ...,
        description="Group name",
        min_length=2, max_length=50
    )


class GroupUpdateRequest(BaseModel):
    """
    Request model for updating a group
    """
    name: str = Field(
        ...,
        description="Group name",
        min_length=2, max_length=50
    )


class PermissionRequest(BaseModel):
    """
    Request model for creating a permission
    """
    name: str = Field(
        ...,
        description="Permission name",
        min_length=2, max_length=50
    )


class PermissionUpdateRequest(BaseModel):
    """
    Request model for updating a permission
    """
    name: str = Field(
        ...,
        description="Permission name",
        min_length=2, max_length=50
    )


class RolePermissionRequest(BaseModel):
    """
    Request model for assigning a permission to a role
    """
    permission_id: UUID = Field(..., description="Permission ID")


class GroupPermissionRequest(BaseModel):
    """
    Request model for assigning a permission to a group
    """
    permission_id: UUID = Field(..., description="Permission ID")


class RoleResponse(BaseModel):
    """
    Response model for a role
    """
    id: UUID
    name: str
    is_deleted: bool

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    """
    Response model for a group
    """
    id: UUID
    name: str
    is_deleted: bool

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    """
    Response model for a permission
    """
    id: UUID
    name: str
    created_by: Optional[UUID] = None
    is_deleted: bool

    class Config:
        from_attributes = True


class ScheduleTypeEnum(str, Enum):
    fixed = "Fixed"
    relative = "Relative"


class InvitationRequest(BaseModel):
    contact: str = Field(
        ..., description="Care receiver's email or mobile number"
    )
    receiver_name: str = Field(
        None, description="Care receiver's name"
    )
    relationship: str = Field(
        None, description="Care receiver's relationship with invitee"
    )


class CheckinScheduleRequest(BaseModel):
    frequency: int = Field(
        ..., description="Frequency of check-ins in hours"
    )
    schedule_type: ScheduleTypeEnum = Field(
        default=ScheduleTypeEnum.fixed, description="Type of schedule (Fixed or Relative)"
    )


class RelationshipRequest(BaseModel):
    """Request model for creating a relationship"""
    name: str = Field(
        ..., 
        description="Relationship name",
        min_length=2, 
        max_length=50
    )
