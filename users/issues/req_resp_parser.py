from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from users.models.issue import IssueStatusEnum, IssuePriorityEnum


class CreateIssueRequest(BaseModel):
    """Request model for creating an issue"""
    subject: str = Field(..., description="Issue subject", min_length=5, max_length=200)
    description: str = Field(..., description="Issue description", min_length=10)
    priority: IssuePriorityEnum = Field(IssuePriorityEnum.MEDIUM, description="Issue priority")
    issue_type_id: Optional[UUID] = Field(None, description="Issue type ID")
    agent_id: Optional[UUID] = Field(None, description="Related agent ID")
    organization_id: Optional[UUID] = Field(None, description="Related organization ID")
    business_id: Optional[UUID] = Field(None, description="Related business ID")


class IssueCommentRequest(BaseModel):
    """Request model for adding a comment to an issue"""
    comment: str = Field(..., description="Comment text", min_length=5)


class IssueCommentResponse(BaseModel):
    """Response model for issue comments"""
    id: UUID
    comment: str
    commented_by: UUID
    commenter_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IssueStatsResponse(BaseModel):
    """Response model for issue statistics"""
    total_issues: int
    open_issues: int
    in_progress_issues: int
    resolved_issues: int
    closed_issues: int
    issues_by_priority: dict
    issues_by_status: dict
    avg_resolution_time_days: Optional[float] = None


class CreateIssueTypeRequest(BaseModel):
    """Request model for creating an issue type"""
    name: str = Field(..., description="Issue type name", min_length=2, max_length=100)


class UpdateIssueStatusRequest(BaseModel):
    """Request model for updating issue status (admin only)"""
    status: IssueStatusEnum = Field(..., description="New status for the issue")


class AdminCommentRequest(BaseModel):
    """Request model for admin to add a comment to an issue"""
    comment: str = Field(..., description="Admin comment text", min_length=5)
    change_status: Optional[IssueStatusEnum] = Field(None, description="Optionally change status while commenting")

