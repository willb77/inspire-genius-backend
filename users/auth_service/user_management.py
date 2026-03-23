import json
from fastapi import APIRouter, Depends, Path, Query, HTTPException
from fastapi_utils.cbv import cbv
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
import secrets
from datetime import timedelta

from users.auth_service.req_resp_parser import (
    ChangeUserRoleRequest, InvitationAcceptRequest, UserEditRequest, UserInviteRequest, BulkUserInviteRequest
)
from users.auth_service.schema import (
    activate_user_and_update_password,
    create_user,
    create_user_invitation,
    delete_user_by_email,
    edit_active_user, get_admin_role_id,
    get_invitation_by_token,
    get_user_by_email,
    regenerate_invitation_token, update_invitation_status,
    get_users_with_invitation_details,
    validate_invitation_token,
    check_existing_invitation
)
from users.auth_service.schema import send_invitation_email_helper
from users.rbac.schema import get_role_by_id
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from users.decorators import (
    require_admin_role, require_role, VALID_ROLES,
    check_organization_access, get_user_accessible_organizations
)
from users.organization.schema import (
    get_organization_by_id,
    check_organization_has_admin,
    check_business_has_admin,
    create_organization_admin
)
from users.aws_wrapper.ses_email_service import send_invitation_email
from users.aws_wrapper.cognito_utils import (
    admin_create_user, delete_cognito_user, generate_temporary_password, admin_set_user_password
)
from users.models.user import InvitationStatusEnum, UserInvitation, Users
from users.models.rbac import Roles
from prism_inspire.db.session import ScopedSession


user_management_routes = APIRouter(prefix="/user-management", tags=["User Management"])

went_wrong = "Something went wrong, please try again later"


class UserInvitationHandler:
    """Helper class to handle user invitation logic and reduce cognitive complexity"""
    
    def __init__(self, user_data: dict):
        self.user_data = user_data
        self.user_id = user_data.get("sub")
        self.inviter_role = user_data.get("user_role", "").lower()
    
    def validate_organization_access(self, data: dict) -> Optional[dict]:
        """Validate organization access permissions"""
        if data.get("organization_id"):
            if not check_organization_access(self.user_data, str(data["organization_id"])):
                return create_response(
                    message="Access denied to this organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )
        return None
    
    def validate_and_get_role(self, role_id: str) -> tuple[dict, str]:
        """Validate role exists and return role name"""
        role = get_role_by_id(role_id)
        if not role:
            error_response = create_response(
                message="Role not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
            return error_response, None
        return None, role.name
    
    def apply_automatic_role_assignment(self, data: dict) -> dict:
        """Apply automatic admin role assignment for super admin invitations"""
        if self.inviter_role == "super-admin" and data.get("organization_id"):
            admin_role_id = get_admin_role_id()
            if admin_role_id:
                data["role_id"] = admin_role_id
                logger.info("Super admin invitation with organization_id: automatically assigning admin role")
            else:
                logger.warning("Could not get admin role ID for automatic assignment")
        return data
    
    def create_cognito_user(self, email: str, role_name: str, first_name: str = None, last_name: str = None) -> dict:
        """Create user in Cognito and return result"""
        temporary_password = generate_temporary_password()

        # Combine first_name and last_name for Cognito's name attribute
        full_name = None
        if first_name and last_name:
            full_name = f"{first_name} {last_name}".strip()
        elif first_name:
            full_name = first_name
        elif last_name:
            full_name = last_name

        cognito_result = admin_create_user(
            email=email,
            temporary_password=temporary_password,
            role_name=role_name,
            user_attributes={"name": full_name} if full_name else {},
        )

        if not cognito_result.get('status'):
            delete_user_by_email(email)
            return create_response(
                message=cognito_result.get('message', 'Failed to create user'),
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        return cognito_result
    
    def create_database_user(self, cognito_result: dict, data: dict) -> str:
        """Create user record in database"""
        user_data = {
            "user_id": cognito_result.get('user_id'),
            "email": data["email"],
            "password": None,  # Password managed by Cognito
            "auth_provider": "cognito",
            "organization_id": data.get("organization_id"),
            "business_id": data.get("business_id"),
            "role_id": data.get("role_id"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "assigned_by": data.get("invited_by")
        }

        user_id = create_user(
            data=user_data,
            is_email_verified=False,
            is_active=False
        )

        if not user_id:
            delete_user_by_email(data["email"])

        return user_id


@cbv(user_management_routes)
class UserManagementView:
    @user_management_routes.post("/invite", response_model=dict)
    def invite_user(
        self,
        invite_request: UserInviteRequest,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Admin-initiated user invitation flow using AWS Cognito and SES
        
        Flow:
        1. Admin invites user with email and role
        2. Create user in Cognito with temporary password
        3. Store invitation record in database
        4. Send SES email invitation with custom template
        Automatically cleans up unconfirmed users from DB & Cognito if any step fails.
        """
        try:
            handler = UserInvitationHandler(user_data)
            data = invite_request.model_dump()
            data["invited_by"] = handler.user_id

            # If no organization_id or business_id, assign 'user' role automatically
            if not data.get("organization_id") and not data.get("business_id"):
                if not data.get("role_id"):
                    from users.rbac.schema import get_role_id
                    user_role_id = get_role_id("user", create_if_missing=True)
                    if user_role_id:
                        data["role_id"] = user_role_id
                        logger.info("No organization/business provided: automatically assigning 'user' role")
                    else:
                        return create_response(
                            message="Failed to get default 'user' role",
                            error_code=SOMETHING_WENT_WRONG,
                            status=False,
                            status_code=500
                        )

            # Validate organization access
            error_response = handler.validate_organization_access(data)
            if error_response:
                return error_response

            # Validate role and get role name
            error_response, role_name = handler.validate_and_get_role(data["role_id"])
            if error_response:
                return error_response
            
            # Check if trying to add admin role to business (must have both org_id and business_id)
            if role_name and role_name.lower() == "admin" and data.get("organization_id") and data.get("business_id"):
                # Check if business already has an admin
                if check_business_has_admin(data["organization_id"], data["business_id"]):
                    return create_response(
                        message="Business already has an admin. Only one admin per business is allowed.",
                        error_code=VALIDATION_ERROR_CODE,
                        status=False,
                        status_code=400
                    )

            # Check if trying to add admin role to organization
            elif role_name and role_name.lower() == "admin" and data.get("organization_id"):
                # Check if organization already has an admin
                if check_organization_has_admin(data["organization_id"]):
                    return create_response(
                        message="Organization already has an admin. Only one admin per organization is allowed.",
                        error_code=VALIDATION_ERROR_CODE,
                        status=False,
                        status_code=400
                    )
            else:
                logger.info("Non-admin role invitation or no organization_id provided: skipping admin existence check")

            # Apply automatic role assignment
            data = handler.apply_automatic_role_assignment(data)

            # Check for existing invitations
            invitation_check = check_existing_invitation(data["email"])
            if invitation_check["should_block"]:
                return create_response(
                    message=invitation_check["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    data=invitation_check["data"],
                    status_code=400
                )

            # Create invitation record
            invitation_result = create_user_invitation(data)
            if not invitation_result:
                return create_response(
                    message="Failed to create user invitation record",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            invitation_id = invitation_result["invitation_id"]
            invitation_token = invitation_result["invitation_token"]

            # Get invitation object
            invitation = get_invitation_by_token(invitation_token)
            if not invitation:
                return create_response(
                    message="Failed to retrieve invitation record",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            # Create Cognito user
            cognito_result = handler.create_cognito_user(
                data["email"],
                role_name,
                data.get("first_name"),
                data.get("last_name")
            )
            if isinstance(cognito_result, dict) and not cognito_result.get('user_id'):
                return cognito_result  # This is an error response

            # Create database user
            user_id = handler.create_database_user(cognito_result, data)
            if not user_id:
                return create_response(
                    message="Failed to create user",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            # Create OrganizationAdmin entry if inviting admin role
            if role_name and role_name.lower() == "admin" and data.get("organization_id"):
                org_admin_id = create_organization_admin(
                    org_id=data["organization_id"],
                    user_id=user_id,
                    assigned_by=handler.user_id
                )
                if not org_admin_id:
                    logger.warning(f"Failed to create OrganizationAdmin entry for user {user_id}")
                else:
                    logger.info(f"Created OrganizationAdmin entry: {org_admin_id}")

            # Send invitation email
            # Combine first_name and last_name for email
            user_name = None
            if data.get("first_name") and data.get("last_name"):
                user_name = f"{data['first_name']} {data['last_name']}"
            elif data.get("first_name"):
                user_name = data.get("first_name")
            elif data.get("last_name"):
                user_name = data.get("last_name")

            email_result = send_invitation_email_helper(
                email=data["email"],
                organization_id=data.get("organization_id"),
                role_name=role_name,
                invitation_token=invitation.invitation_token,
                user_name=user_name
            )
            if not email_result.get("status"):
                delete_user_by_email(data["email"])
                return create_response(
                    message="Failed to send invitation email",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            return create_response(
                message="User invitation sent successfully. User account created and will be activated upon invitation acceptance.",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "invitation_id": invitation_id,
                    "user_id": user_id,
                    "cognito_user_id": cognito_result.get('user_id'),
                    "user_created": True,
                    "profile_created": True,
                    "user_status": "inactive_pending_invitation",
                    "email_sent": email_result.get("status", False)
                }
            )
                
        except Exception as e:
            logger.error(f"Error inviting user: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )


    @user_management_routes.post("/invitations/accept", response_model=dict)
    def accept_invitation(
        self,
        accept_request: InvitationAcceptRequest
    ):
        """
        Accept invitation and set permanent password with comprehensive validation

        Enhanced Flow:
        1. Validate invitation token and status with automatic expiration handling
        2. Prevent multiple acceptances of the same invitation (returns specific error)
        3. Check for existing user conflicts
        4. Set permanent password using admin challenge response
        5. Create database records (Users and UserProfile)
        6. Ensure proper user activation and email verification
        7. Update invitation status with validation and timestamp
        8. Perform post-acceptance verification with detailed logging

        Multiple Acceptance Prevention:
        - Automatically detects if invitation has already been accepted
        - Returns specific error message with acceptance timestamp
        - Prevents duplicate user creation and profile conflicts
        """
        try:
            # Enhanced validation using centralized function
            validation_result = validate_invitation_token(accept_request.invitation_token)

            if not validation_result['valid']:
                error_code_mapping = {
                    'INVALID_TOKEN': NOT_FOUND,
                    'INVITATION_EXPIRED': VALIDATION_ERROR_CODE,
                    'ALREADY_ACCEPTED': VALIDATION_ERROR_CODE,
                    'INVALID_STATUS': VALIDATION_ERROR_CODE,
                    'VALIDATION_ERROR': SOMETHING_WENT_WRONG
                }

                status_code = 404 if validation_result['error_code'] == 'INVALID_TOKEN' else 400
                return create_response(
                    message=validation_result['message'],
                    error_code=error_code_mapping.get(validation_result['error_code'], SOMETHING_WENT_WRONG),
                    status=False,
                    data={
                        'error_type': validation_result['error_code'],
                        'current_status': validation_result.get('current_status'),
                        'expires_at': validation_result.get('expires_at'),
                        'accepted_at': validation_result.get('accepted_at')
                    },
                    status_code=status_code
                )

            invitation = validation_result['invitation']

            # Check if invitation has expired and update status if needed
            current_time = datetime.now(timezone.utc)
            expires_at = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at

            if invitation.status == InvitationStatusEnum.PENDING and current_time > expires_at:
                # Update status to expired on access
                update_invitation_status(invitation.id, InvitationStatusEnum.EXPIRED)
                return create_response(
                    message="Invitation has expired",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    data={
                        'current_status': InvitationStatusEnum.EXPIRED.value,
                        'expired_at': expires_at.isoformat()
                    },
                    status_code=400
                )

            if invitation.status != InvitationStatusEnum.PENDING:
                return create_response(
                    message=f"Invitation is not available for acceptance. Status: {invitation.status.value}",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            # Check if user already exists and is active (handle edge cases)
            existing_user = get_user_by_email(invitation.email)
            if existing_user and existing_user.is_active:
                # User already exists and is active, mark invitation as accepted
                update_invitation_status(invitation.id, InvitationStatusEnum.ACCEPTED)
                return create_response(
                    message="User account already exists and is active. You can log in with your existing password.",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={
                        "email": invitation.email,
                        "invitation_accepted": True,
                        "already_activated": True,
                        "can_login": True
                    }
                )

            # Verify that inactive user exists (should exist from invitation creation)
            if not existing_user:
                logger.error(f"No user record found for invitation acceptance: {invitation.email}")
                return create_response(
                    message="User account not found. Please contact support.",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=404
                )

            # Set permanent password using admin privileges (correct approach for invitations)
            password_result = admin_set_user_password(
                username=invitation.email,
                password=accept_request.new_password,
                permanent=True
            )

            if not password_result.get('status'):
                return create_response(
                    message="Failed to set password",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    description=password_result.get('message'),
                    status_code=500
                )

            # Activate user and update password in database
            activation_success = activate_user_and_update_password(invitation.email, accept_request.new_password)

            if not activation_success:
                logger.error(f"Failed to activate user account for {invitation.email}")
                return create_response(
                    message="Failed to activate user account. Please contact support.",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            user_id = str(existing_user.user_id)

            # Update invitation status to accepted with timestamp
            status_updated = update_invitation_status(invitation.id, InvitationStatusEnum.ACCEPTED)

            if not status_updated:
                logger.error(f"Failed to update invitation status for {invitation.email}")
                return create_response(
                    message="Failed to complete invitation acceptance. Please contact support.",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            logger.info(f"Invitation accepted successfully for {invitation.email} - User activated from inactive state")

            return create_response(
                message="Invitation accepted successfully. Your account has been activated and you can now log in with your password.",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "email": invitation.email,
                    "user_id": user_id,
                    "invitation_id": str(invitation.id),
                    "invitation_accepted": True,
                    "password_set": True,
                    "user_activated": True,
                    "profile_activated": True,
                    "email_verified": True,
                    "can_login": True,
                    "activation_method": "existing_user_activated",
                    "organization_id": str(invitation.organization_id) if invitation.organization_id else None
                }
            )

        except Exception as e:
            logger.error(f"Error accepting invitation: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )


    @user_management_routes.get("/users", response_model=dict)
    def list_users(
        self,
        organization_id: Optional[UUID] = Query(None, description="Filter by organization ID"),
        business_id: Optional[UUID] = Query(None, description="Filter by business ID"),
        invitation_status: Optional[str] = Query(None, description="Comma-separated: invitation_sent,accepted,expired"),
        user_status: Optional[str] = Query(None, description="Comma-separated: active,deactivated,awaiting"),
        role: Optional[str] = Query(None, description="Comma-separated role names"),
        search: Optional[str] = Query(None, description="Search by name or email"),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=100),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        List users with comprehensive filtering options:
        
        Invitation Status Filters:
        - invitation_sent: Invitations sent but not accepted
        - accepted: Invitations that were accepted
        - expired: Invitations that expired
        
        User Status Filters:
        - active: Active user accounts
        - deactivated: Inactive user accounts
        - awaiting: Invitation send not accepted or expired
        
        Examples:
        - ?invitation_status=invitation_sent,expired
        - ?user_status=active
        - ?invitation_status=invitation_sent&user_status=deactivated
        """
        try:
            # Validate invitation status filter
            invitation_status_list = None
            if invitation_status:
                invitation_status_list = [s.strip().lower() for s in invitation_status.split(',') if s.strip()]
                valid_invitation_statuses = ['invitation_sent', 'accepted', 'expired']
                invalid_statuses = [s for s in invitation_status_list if s not in valid_invitation_statuses]
                if invalid_statuses:
                    return create_response(
                        message=f"Invalid invitation status values: {', '.join(invalid_statuses)}. Valid options: {', '.join(valid_invitation_statuses)}",
                        error_code=VALIDATION_ERROR_CODE,
                        status=False,
                        status_code=400
                    )

            # Validate user status filter
            user_status_list = None
            if user_status:
                user_status_list = [s.strip().lower() for s in user_status.split(',') if s.strip()]
                valid_user_statuses = ['active', 'deactivated', 'awaiting']
                invalid_statuses = [s for s in user_status_list if s not in valid_user_statuses]
                if invalid_statuses:
                    return create_response(
                        message=f"Invalid user status values: {', '.join(invalid_statuses)}. Valid options: {', '.join(valid_user_statuses)}",
                        error_code=VALIDATION_ERROR_CODE,
                        status=False,
                        status_code=400
                    )

            role_list = None
            if role:
                role_list = [r.strip() for r in role.split(',') if r.strip()]

            # Check access permissions
            if organization_id and not check_organization_access(user_data, str(organization_id)):
                return create_response(
                    message="Access denied to this organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Get filtered users
            result = get_users_with_invitation_details(
                organization_id=str(organization_id) if organization_id else None,
                business_id=str(business_id) if business_id else None,
                invitation_status_list=invitation_status_list,
                user_status_list=user_status_list,
                role_list=role_list,
                search=search,
                page=page,
                limit=limit
            )

            if not result:
                return create_response(
                    message="Failed to retrieve users",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )
            # ✅ Exclude users with 'super-admin' role
            if "data" in result and isinstance(result["data"], dict) and "users" in result["data"]:
                result["data"]["users"] = [
                    user for user in result["data"]["users"]
                    if user.get("role", "").lower() != "super-admin"
                ]

            return create_response(
                message="Users retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=result
            )

        except Exception as e:
            logger.error(f"Error listing users: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message="Failed to retrieve users. Please try again.",
                status=False,
                status_code=500
            )

    @user_management_routes.delete("/users/{user_email}", response_model=dict)
    def delete_user(
        self,
        user_email: str = Path(..., description="Email of user to delete"),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Delete user with different logic based on status:
        - If user is not confirmed (invitation pending/expired): Hard delete from database
        - If user is active: Soft delete (set is_deleted = True)
        """
        try:
            # Check organization access if needed
            session = ScopedSession()
            try:
                user = session.query(Users).filter(Users.email == user_email).first()
                if user and user.profile and user.profile.org_id:
                    if not check_organization_access(user_data, str(user.profile.org_id)):
                        return create_response(
                            message="Access denied to delete users from this organization",
                            error_code=FORBIDDEN_ERROR_CODE,
                            status=False,
                            status_code=403
                        )
            finally:
                session.close()
                ScopedSession.remove()

                # Perform deletion
            result = delete_user_by_email(user_email)

            if result["success"]:
                return create_response(
                    message=result["message"],
                    error_code=SUCCESS_CODE,
                    status=True,
                    data=result["data"]
                )
            else:
                return create_response(
                    message=result["message"],
                    error_code=result.get("error_code", SOMETHING_WENT_WRONG),
                    status=False,
                    status_code=500
                )

        except Exception as e:
            logger.error(f"Error deleting user {user_email}: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message="Failed to delete user. Please try again.",
                status=False,
                status_code=500
            )

    @user_management_routes.post("/invite/bulk", response_model=dict)
    def bulk_invite_users(
        self,
        bulk_request: BulkUserInviteRequest,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Bulk user invitation - processes list of users with same parameters as single invite
        """
        try:
            successful_invitations = []
            failed_invitations = []
            
            for index, user_invite in enumerate(bulk_request.users):
                try:
                    # Call existing invite_user method directly
                    result = self.invite_user(user_invite, user_data)
                    
                    # Extract data from JSONResponse object
                    if hasattr(result, 'body'):
                        result_data = json.loads(result.body.decode())
                    else:
                        result_data = result
                    
                    if result_data.get("status"):
                        successful_invitations.append({
                            "index": index,
                            "email": user_invite.email,
                            "name": user_invite.name,
                            "result": result_data.get("data", {})
                        })
                    else:
                        failed_invitations.append({
                            "index": index,
                            "email": user_invite.email,
                            "name": user_invite.name,
                            "error": result_data.get("message"),
                            "description": result_data.get("description"),
                            "error_code": result_data.get("error_code")
                        })
                    
                except Exception as e:
                    failed_invitations.append({
                        "index": index,
                        "email": user_invite.email,
                        "name": user_invite.name,
                        "error": f"Processing error: {str(e)}",
                        "error_code": "PROCESSING_ERROR"
                    })
            
            total = len(bulk_request.users)
            success_count = len(successful_invitations)
            failed_count = len(failed_invitations)
            
            return create_response(
                message=f"Processed {total} invitations: {success_count} successful, {failed_count} failed",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "summary": {
                        "total": total,
                        "successful": success_count,
                        "failed": failed_count
                    },
                    "successful_invitations": successful_invitations,
                    "failed_invitations": failed_invitations
                }
            )
            
        except Exception as e:
            logger.error(f"Bulk invitation error: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message="Bulk invitation failed",
                status=False,
                status_code=500
            )

    @user_management_routes.post("/invitations/{invitation_id}/resend", response_model=dict)
    def resend_invitation(
        self,
        invitation_id: str = Path(..., description="Invitation ID to resend"),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Resend invitation email with new token and extended expiration
        Hard deletes previous invitations for the same email
        """
        try:
            # Regenerate invitation token
            token_result = regenerate_invitation_token(invitation_id, extend_days=3)
            
            if not token_result['success']:
                return create_response(
                    message=token_result['error'],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            # Send email using helper function (it handles organization lookup internally)
            email_result = send_invitation_email_helper(
                email=token_result['email'],
                organization_id=token_result.get('organization_id'),
                role_name=token_result.get('role_name', 'Member'),
                invitation_token=token_result['invitation_token'],
                user_name=""
            )

            logger.info(f"Resent invitation for {token_result['email']}")

            return create_response(
                message="Invitation resent successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "invitation_id": invitation_id,
                    "email": token_result['email'],
                    "new_token": token_result['invitation_token'],
                    "expires_at": token_result['expires_at'],
                    "email_sent": email_result.get("status", False),
                }
            )

        except Exception as e:
            logger.error(f"Error resending invitation {invitation_id}: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message="Failed to resend invitation",
                status=False,
                status_code=500
            )

    @user_management_routes.put("/users/{user_email}/edit", response_model=dict)
    def edit_user(
        self,
        edit_request: UserEditRequest,
        user_email: str = Path(..., description="Email of user to edit"),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Edit active user details (name, status, role)
        Cannot edit users with pending/expired/accepted invitations
        """
        try:
            fields_to_update = edit_request.model_dump(exclude_unset=True)
            result = edit_active_user(user_email, fields_to_update)

            if result["success"]:
                return create_response(
                    message=result["message"],
                    error_code=SUCCESS_CODE,
                    status=True,
                    data=result["data"]
                )
            else:
                return create_response(
                    message=result["message"],
                    error_code=result.get("error_code", SOMETHING_WENT_WRONG),
                    status=False,
                    status_code=400
                )

        except Exception as e:
            logger.error(f"Error editing user {user_email}: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message="Failed to edit user",
                status=False,
                status_code=500
            )


@user_management_routes.put("/users/{user_id}/role", response_model=dict)
def change_user_role(
    role_request: ChangeUserRoleRequest,
    user_id: str = Path(..., description="User ID whose role to change"),
    user_data: dict = Depends(require_role("super-admin")),
):
    """
    Change a user's role (super-admin only).

    PUT /v1/user-management/users/{user_id}/role
    Body: { "role": "coach-admin" }
    """
    try:
        new_role_name = role_request.role.lower()

        if new_role_name not in VALID_ROLES:
            return create_response(
                message=f"Invalid role '{role_request.role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400,
            )

        session = ScopedSession()
        try:
            from users.models.user import UserProfile
            from users.rbac.schema import get_role_id as _get_role_id

            # Get or create the target role
            new_role_id = _get_role_id(new_role_name, create_if_missing=True)
            if not new_role_id:
                return create_response(
                    message="Failed to resolve target role",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500,
                )

            # Find the user and their profile
            user = session.query(Users).filter(Users.user_id == user_id).first()
            if not user:
                return create_response(
                    message="User not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404,
                )

            profile = session.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            if not profile:
                return create_response(
                    message="User profile not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404,
                )

            # Determine previous role name
            previous_role_name = None
            if profile.role:
                prev_role = session.query(Roles).filter(Roles.id == profile.role).first()
                previous_role_name = prev_role.name if prev_role else None

            # Update the role
            profile.role = new_role_id
            session.commit()

            logger.info(
                f"Role changed for user {user_id}: "
                f"{previous_role_name} -> {new_role_name} "
                f"(by {user_data.get('sub')})"
            )

            return create_response(
                message="User role updated successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "user_id": user_id,
                    "email": user.email,
                    "previous_role": previous_role_name,
                    "new_role": new_role_name,
                },
            )
        finally:
            session.close()
            ScopedSession.remove()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing role for user {user_id}: {str(e)}")
        return create_response(
            error_code=SOMETHING_WENT_WRONG,
            message="Failed to change user role",
            status=False,
            status_code=500,
        )
