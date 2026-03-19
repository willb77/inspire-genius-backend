from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import List, Optional

# Reused description for new password fields
NEW_PASSWORD_DESC = "New password for the user account"


class SignupRequest(BaseModel):
    email: str = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")
    confirm_password: str = Field(..., description="Confirm the password")
    role: Optional[str] = Field(
        None,
        description="Optional role name (defaults to 'user'). "
                    "Valid values: user, super-admin, coach-admin, org-admin, prompt-engineer"
    )

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'SignupRequest':
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    email: str = Field(..., description="User's email address")
    password: str = Field(..., description="User's password")
    verification: Optional[bool] = False
    session: Optional[str] = None
    otp: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# Social Login Schemas
class SocialLoginRequest(BaseModel):
    provider: str = Field(
        ...,
        description="Social provider: google or facebook"
    )


class SocialCallbackRequest(BaseModel):
    code: str = Field(..., description="Authorization code from Cognito")


# User Management Schemas
class UserInviteRequest(BaseModel):
    """Request model for inviting a user"""
    email: EmailStr = Field(
        ...,
        description="Email address of the user to invite"
    )
    first_name: str = Field(
        ...,
        description="First name of the user to invite",
        min_length=1,
        max_length=50
    )
    last_name: str = Field(
        ...,
        description="Last name of the user to invite",
        min_length=1,
        max_length=50
    )
    role_id: Optional[UUID] = Field(
        None,
        description="Role ID to assign to the user"
    )
    organization_id: Optional[UUID] = Field(
        None,
        description="Organization ID to assign user to"
    )
    business_id: Optional[UUID] = Field(
        None,
        description="Business ID to assign user to"
    )


class InvitationAcceptRequest(BaseModel):
    """Request model for accepting an invitation"""
    invitation_token: str = Field(
        ...,
        description="Invitation token from email"
    )
    new_password: str = Field(
        ...,
        description=NEW_PASSWORD_DESC,
        min_length=8
    )


class RequestPasswordResetRequest(BaseModel):
    """Request model for initiating password reset"""
    email: str = Field(..., description="User email address")


class ResetPasswordRequest(BaseModel):
    """Request model for completing password reset with token"""
    reset_token: str = Field(..., description="Password reset token from email")
    new_password: str = Field(
        ...,
        description=NEW_PASSWORD_DESC,
        min_length=8,
        max_length=128
    )
    confirm_password: str = Field(
        ...,
        description="Confirm new password",
        min_length=8,
        max_length=128
    )

    @model_validator(mode='after')
    def validate_passwords_match(self):
        """Validate that password and confirm_password match"""
        if self.new_password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self


class ChangePasswordRequest(BaseModel):
    """Request model for changing password (authenticated users)"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        description=NEW_PASSWORD_DESC,
        min_length=8,
        max_length=128
    )
    confirm_password: str = Field(
        ...,
        description="Confirm new password",
        min_length=8,
        max_length=128
    )

    @model_validator(mode='after')
    def validate_passwords_match(self):
        """Validate that new_password and confirm_password match"""
        if self.new_password != self.confirm_password:
            raise ValueError('New password and confirm password do not match')
        return self


class BulkUserInviteRequest(BaseModel):
    """Request model for bulk user invitations"""
    users: List[UserInviteRequest] = Field(
        ...,
        description="List of users to invite (same format as single invite)",
        min_items=1,
        max_items=50
    )


class UserEditRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    is_active: Optional[bool] = None
    role_id: Optional[UUID] = None

    class Config:
        extra = "forbid"


class ChangeUserRoleRequest(BaseModel):
    """Request model for changing a user's role (super-admin only)"""
    role: str = Field(
        ...,
        description="New role name. Valid values: user, super-admin, coach-admin, org-admin, prompt-engineer"
    )
