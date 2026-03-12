from datetime import datetime, timedelta, timezone
import secrets
import uuid
from prism_inspire.db.session import ScopedSession
from users.aws_wrapper.cognito_utils import delete_cognito_user, get_cognito_username_by_user_id, update_cognito_user_attributes
from users.aws_wrapper.ses_email_service import send_invitation_email
from users.models.rbac import Roles
from users.models.user import InvitationStatusEnum, UserInvitation, Users, UserProfile
from users.auth_service.utils import generate_hash, get_full_name
from prism_inspire.core.log_config import logger
from users.organization.schema import get_organization_by_id
from users.rbac.schema import add_user_to_group, get_role_by_id, get_role_id
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, func, or_, select
from typing import Any, Dict, List, Optional

# Import response codes
NOT_FOUND = "NOT_FOUND"
SOMETHING_WENT_WRONG = "SOMETHING_WENT_WRONG"


def update_user_verification_status(
    email: str, is_verified: bool = True, is_active: bool = True
):
    """
    Update user's email verification and active status

    Args:
        email: User's email address
        is_verified: Email verification status
        is_active: User active status

    Returns:
        True if successful, False otherwise
    """
    try:
        session = ScopedSession()
        user = session.query(Users).filter(Users.email == email).first()
        if user:
            user.is_email_verified = is_verified
            user.is_active = is_active

            # Also activate the user profile if activating the user
            if is_active:
                profile = session.query(UserProfile).filter(UserProfile.user_id == str(user.user_id)).first()
                if profile:
                    profile.is_active = True
                    logger.info(f"Activated user profile for: {email}")
                else:
                    logger.warning(f"No profile found for user {email} during activation")

            session.commit()
            logger.info(f"Updated verification status for user: {email}")

            # Now assign the user to a group
            assigned = add_user_to_group(user.user_id, "user")
            if not assigned:
                logger.warning(
                    "Verification succeeded but failed to assign to group: "
                    f"{email}"
                )
                return False

            return True
        else:
            logger.warning(f"User not found with email: {email}")
            return False
    except Exception as e:
        logger.exception(f"Error updating user verification status: {e}")
        session.rollback()
        return False
    finally:
        session.close()
        ScopedSession.remove()


def get_user_by_email(email: str):
    """
    Get user by email address

    Args:
        email: User's email address

    Returns:
        User object if found, None otherwise
    """
    session = ScopedSession()
    try:
        user = session.query(Users).options(
            joinedload(Users.profile)
        ).filter(Users.email == email).first()
        return user
    except Exception as e:
        logger.exception(f"Error getting user by email: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def create_user(data, is_email_verified=False, is_active=False):
    """
    Create a new user in the database

    Args:
        data: Dictionary containing user data
        (user_id, password, email, auth_provider, user_group, organization_id)
              - password can be None for social login users (Google/Facebook)
              - organization_id: Organization ID to associate with user
        is_email_verified: Email verification status (default: False)
        is_active: User active status (default: False)

    Returns:
        User ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Hash the password only if it's provided (not None for social users)
        password = data.get("password")
        hashed_password = (
            generate_hash(password)
            if password is not None else None
        )

        # Create new user object
        new_user = Users(
            user_id=data.get("user_id"),
            password=hashed_password,
            email=data.get("email"),
            auth_provider=data.get("auth_provider", "cognito"),
            is_email_verified=is_email_verified,
            is_active=is_active
        )

        # Add and commit to database
        session.add(new_user)
        session.commit()

        user_id = str(new_user.user_id)
        # Create user profile with organization_id if provided
        organization_id = data.get("organization_id")
        role_id = data.get("role_id")  # Get role_id if provided
        first_name = data.get("first_name")   # Get user first name if provided
        last_name = data.get("last_name")     # Get user last name if provided

        if organization_id or role_id:
            try:
                profile = UserProfile(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    first_name=first_name,
                    last_name=last_name,
                    role=role_id,
                    org_id=organization_id,
                    business_id=data.get("business_id"),
                    assigned_by=data.get("assigned_by"),
                    is_active=is_active,
                    is_profile_complete=False
                )
                session.add(profile)
                session.commit()
                logger.info(f"Created user profile for user {user_id} with organization {organization_id}")

            except Exception as e:
                logger.warning(f"Failed to create user profile: {e}")

        logger.info("New user created")
        return user_id
    except Exception as e:
        logger.exception(f"Error creating user: {e}")
        session.rollback()
    finally:
        session.close()
        ScopedSession.remove()
    return None


def search_user_by_name(session, search_term: str) -> List[Users]:
    """
    Searches for users by a partial name match, ignoring case.

    Args:
        session: The SQLAlchemy Session object.
        search_term: The partial name to search for (e.g., "john", "Doe", "smi").

    Returns:
        List[Users]: A list of User objects that match the search term.
    """
    if not search_term:
        return []

    # The '%' are wildcards. '%term%' means the term can appear anywhere in the name.
    # The .ilike() method performs a case-insensitive search in PostgreSQL.
    search_pattern = f"%{search_term}%"
    
    # Join with profile to search in the name field
    query = select(Users).where(
        Users.email.ilike(search_pattern)
    )
    
    # Execute the query and return all matching User objects
    matching_users = session.execute(query).scalars().all()
    
    return matching_users


# User Invitation CRUD Operations
def create_user_invitation(data: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Create a user invitation

    Args:
        data: Dictionary containing invitation data

    Returns:
        Dictionary with invitation_id and invitation_token if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Generate unique invitation token
        invitation_token = secrets.token_urlsafe(32)
        
        # Set expiration to 3 days from now
        expires_at = datetime.now(timezone.utc) + timedelta(days=3)
        
        invitation = UserInvitation(
            id=uuid.uuid4(),
            email=data["email"],
            organization_id=data.get("organization_id"),
            business_id=data.get("business_id"),
            role_id=data["role_id"],
            invitation_token=invitation_token,
            status=InvitationStatusEnum.PENDING,
            invited_by=data.get("invited_by"),
            expires_at=expires_at
        )
        
        session.add(invitation)
        session.commit()

        logger.info(f"User invitation created: {invitation.id}")
        return {
            "invitation_id": str(invitation.id),
            "invitation_token": invitation_token
        }
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating user invitation: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_invitation_by_token(token: str) -> Optional[UserInvitation]:
    """
    Get invitation by token
    
    Args:
        token: Invitation token
        
    Returns:
        UserInvitation object if found, None otherwise
    """
    session = ScopedSession()
    try:
        return session.query(UserInvitation).filter(
            UserInvitation.invitation_token == token
        ).first()
        
    except Exception as e:
        logger.error(f"Error fetching invitation by token: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def validate_invitation_token(invitation_token: str, auto_update_expired: bool = True) -> Dict[str, Any]:
    """
    Comprehensive invitation token validation with automatic expiration handling

    Args:
        invitation_token: The invitation token to validate
        auto_update_expired: Whether to automatically update expired invitations to EXPIRED status

    Returns:
        Dictionary containing validation results and invitation data
    """
    try:
        invitation = get_invitation_by_token(invitation_token)

        if not invitation:
            return {
                'valid': False,
                'error_code': 'INVALID_TOKEN',
                'message': 'Invalid invitation token',
                'invitation': None
            }

        # Check expiration
        current_time = datetime.now(timezone.utc)
        expires_at = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at
        is_expired = current_time > expires_at

        # Auto-update expired invitations
        if is_expired and invitation.status == InvitationStatusEnum.PENDING and auto_update_expired:
            update_success = update_invitation_status(invitation.id, InvitationStatusEnum.EXPIRED)
            if update_success:
                invitation.status = InvitationStatusEnum.EXPIRED  # Update local object
                logger.info(f"Auto-updated expired invitation {invitation.id} to EXPIRED status")

        # Determine validation result based on status and expiration
        if invitation.status == InvitationStatusEnum.EXPIRED or is_expired:
            return {
                'valid': False,
                'error_code': 'INVITATION_EXPIRED',
                'message': 'Invitation has expired',
                'invitation': invitation,
                'expires_at': expires_at.isoformat(),
                'current_status': invitation.status.value
            }
        elif invitation.status == InvitationStatusEnum.ACCEPTED:
            return {
                'valid': False,
                'error_code': 'ALREADY_ACCEPTED',
                'message': 'Invitation has already been accepted',
                'invitation': invitation,
                'current_status': invitation.status.value,
                'accepted_at': invitation.accepted_at.isoformat() if invitation.accepted_at else None
            }
        elif invitation.status == InvitationStatusEnum.PENDING:
            return {
                'valid': True,
                'error_code': None,
                'message': 'Invitation is valid and pending',
                'invitation': invitation,
                'current_status': invitation.status.value,
                'expires_at': expires_at.isoformat()
            }
        else:
            return {
                'valid': False,
                'error_code': 'INVALID_STATUS',
                'message': f'Invitation has invalid status: {invitation.status.value}',
                'invitation': invitation,
                'current_status': invitation.status.value
            }

    except Exception as e:
        logger.error(f"Error validating invitation token: {str(e)}")
        return {
            'valid': False,
            'error_code': 'VALIDATION_ERROR',
            'message': 'Error validating invitation token',
            'invitation': None
        }


def update_invitation_status(invitation_id: str, status: InvitationStatusEnum) -> bool:
    """
    Update invitation status

    Args:
        invitation_id: Invitation ID
        status: New status

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        invitation = session.query(UserInvitation).filter(
            UserInvitation.id == invitation_id
        ).first()

        if not invitation:
            return False

        invitation.status = status
        if status == InvitationStatusEnum.ACCEPTED:
            invitation.accepted_at = datetime.now(timezone.utc)
        invitation.updated_at = datetime.now(timezone.utc)

        session.commit()

        logger.info(f"Invitation status updated: {invitation_id} -> {status}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating invitation status: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def regenerate_invitation_token(invitation_id: str, extend_days: int = 3) -> Dict[str, Any]:
    """
    Regenerate invitation token and extend expiration

    Args:
        invitation_id: Invitation ID to regenerate token for
        extend_days: Number of days to extend expiration from current time (default: 3)

    Returns:
        Dictionary with new token and expiration info, or error details
    """
    session = ScopedSession()
    try:
        invitation = session.query(UserInvitation).filter(
            UserInvitation.id == invitation_id
        ).first()

        if not invitation:
            return {
                'success': False,
                'error': 'Invitation not found',
                'error_code': 'NOT_FOUND'
            }

        # Generate new token and extend expiration
        new_token = secrets.token_urlsafe(32)
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=extend_days)

        # Update invitation
        invitation.invitation_token = new_token
        invitation.expires_at = new_expires_at
        invitation.updated_at = datetime.now(timezone.utc)
        invitation.status = InvitationStatusEnum.PENDING

        session.commit()

        logger.info(f"Regenerated invitation token for {invitation.email}, new expiration: {new_expires_at}")

        return {
            'success': True,
            'invitation_token': new_token,
            'expires_at': new_expires_at.isoformat(),
            'email': invitation.email,
            'invitation_id': str(invitation.id),
            'organization_id': str(invitation.organization_id) if invitation.organization_id else None,
            'role_name': get_role_by_id(invitation.role_id).name if get_role_by_id(invitation.role_id) else '',
            'status': invitation.status.value
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error regenerating invitation token: {str(e)}")
        return {
            'success': False,
            'error': 'Failed to regenerate invitation token',
            'error_code': 'REGENERATION_ERROR'
        }
    finally:
        session.close()
        ScopedSession.remove()


def get_admin_role_id() -> Optional[str]:
    """
    Get the admin role ID, creating it if it doesn't exist

    Returns:
        Admin role ID as string, or None if failed
    """
    try:
        admin_role_id = get_role_id("admin", create_if_missing=True)
        return admin_role_id
    except Exception as e:
        logger.error(f"Failed to get admin role ID: {e}")
        return None


class UserInvitationQueryBuilder:
    """Helper class to build and execute user invitation queries with reduced complexity"""
    
    def __init__(self, session):
        self.session = session
        self.invitation_status_map = {
            "invitation_sent": InvitationStatusEnum.PENDING,
            "accepted": InvitationStatusEnum.ACCEPTED,
            "expired": InvitationStatusEnum.EXPIRED
        }
    
    def build_base_query(self, invitation_status_list: List[str] = None):
        """Build base query with appropriate joins"""
        query = self.session.query(Users).options(joinedload(Users.profile))
        
        if invitation_status_list and not any(s.lower() == "accepted" for s in invitation_status_list):
            query = query.join(UserInvitation, Users.email == UserInvitation.email)
        else:
            query = query.outerjoin(UserInvitation, Users.email == UserInvitation.email)
        
        return query.join(UserProfile, Users.user_id == UserProfile.user_id)
    
    def apply_organization_filters(self, query, organization_id: str = None, business_id: str = None):
        """Apply organization and business filters"""
        if not organization_id and not business_id:
            return query.filter(
                UserProfile.role.isnot(None),
                UserProfile.org_id.is_(None),
                UserProfile.business_id.is_(None)
            )
        elif organization_id and not business_id:
            return query.filter(UserProfile.org_id == organization_id)
        elif organization_id and business_id:
            return query.filter(UserProfile.business_id == business_id)
        return query
    
    def apply_invitation_status_filters(self, query, invitation_status_list: List[str] = None):
        """Apply invitation status filters"""
        if not invitation_status_list:
            return query
        
        conditions = []
        for status in invitation_status_list:
            status_lower = status.lower()
            if status_lower in self.invitation_status_map:
                if status_lower == "accepted":
                    conditions.append(or_(
                        UserInvitation.status == InvitationStatusEnum.ACCEPTED,
                        UserInvitation.status.is_(None)
                    ))
                else:
                    conditions.append(UserInvitation.status == self.invitation_status_map[status_lower])
        
        return query.filter(or_(*conditions)) if conditions else query
    
    def apply_user_status_filters(self, query, user_status_list: List[str] = None):
        """Apply user status filters"""
        if not user_status_list:
            return query
        
        status_filters = []
        for status in user_status_list:
            status_lower = status.lower()
            if status_lower == "active":
                status_filters.append(Users.is_active.is_(True))
            elif status_lower == "deactivated":
                status_filters.append(and_(
                    Users.is_active.is_(False),
                    or_(
                        UserInvitation.status == InvitationStatusEnum.ACCEPTED,
                        UserInvitation.status.is_(None)
                    )
                ))
            elif status_lower == "awaiting":
                status_filters.append(and_(
                    Users.is_active.is_(False),
                    UserInvitation.status == InvitationStatusEnum.PENDING
                ))
        
        return query.filter(or_(*status_filters)) if status_filters else query
    
    def apply_role_filters(self, query, role_list: List[str] = None):
        """Apply role filters"""
        if not role_list:
            return query
        
        role_subq = self.session.query(UserProfile.user_id).join(
            Roles, UserProfile.role == Roles.id
        ).filter(Roles.name.in_(role_list))
        
        return query.filter(Users.user_id.in_(role_subq))
    
    def apply_search_filters(self, query, search: str = None):
        """Apply search filters"""
        if not search:
            return query
        
        search_term = f"%{search.lower()}%"
        return query.filter(or_(
            func.lower(Users.email).like(search_term),
            func.lower(UserProfile.name).like(search_term)
        ))


class UserInvitationDataProcessor:
    """Helper class to process user invitation data"""
    
    def __init__(self, session):
        self.session = session
    
    def get_latest_invitation(self, email: str) -> Optional[UserInvitation]:
        """Get latest invitation for email"""
        return self.session.query(UserInvitation).filter(
            UserInvitation.email == email
        ).order_by(UserInvitation.invited_at.desc()).first()
    
    def handle_expired_invitation(self, invitation: UserInvitation) -> UserInvitation:
        """Handle expired invitation auto-update"""
        if invitation and invitation.status == InvitationStatusEnum.PENDING:
            current_time = datetime.now(timezone.utc)
            expires_at = (invitation.expires_at.replace(tzinfo=timezone.utc)
                          if invitation.expires_at and invitation.expires_at.tzinfo is None
                          else invitation.expires_at)
            if expires_at and current_time > expires_at:
                update_invitation_status(invitation.id, InvitationStatusEnum.EXPIRED)
                invitation.status = InvitationStatusEnum.EXPIRED
        return invitation
    
    def get_user_role_name(self, user: Users) -> Optional[str]:
        """Get role name for user"""
        if user.profile and user.profile.role:
            role = self.session.query(Roles).filter(Roles.id == user.profile.role).first()
            return role.name if role else None
        return None
    
    def map_invitation_status(self, invitation: Optional[UserInvitation]) -> str:
        """Map invitation status to output format"""
        if not invitation or invitation.status is None:
            return "accepted"
        elif invitation.status == InvitationStatusEnum.PENDING:
            return "invitation_sent"
        elif invitation.status == InvitationStatusEnum.ACCEPTED:
            return "accepted"
        elif invitation.status == InvitationStatusEnum.EXPIRED:
            return "expired"
        else:
            return invitation.status.value
    
    def map_user_status(self, user: Users, invitation: Optional[UserInvitation]) -> str:
        """Map user status to output format"""
        if (invitation and invitation.status in [InvitationStatusEnum.PENDING, InvitationStatusEnum.EXPIRED] 
            and not user.is_active):
            return "awaiting"
        elif not user.is_active and (not invitation or invitation.status is None or invitation.status == InvitationStatusEnum.ACCEPTED):
            return "deactivated"
        else:
            return "active" if user.is_active else "deactivated"
    
    def process_user_data(self, user: Users) -> dict:
        """Process single user data"""
        invitation = self.get_latest_invitation(user.email)
        invitation = self.handle_expired_invitation(invitation)
        role_name = self.get_user_role_name(user)
        inv_status_out = self.map_invitation_status(invitation)
        user_status_out = self.map_user_status(user, invitation)

        # Get first_name and last_name from profile
        first_name = user.profile.first_name if user.profile else None
        last_name = user.profile.last_name if user.profile else None
        full_name = user.profile.full_name if user.profile else None

        return {
            "user_id": str(user.user_id),
            "email": user.email,
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "role": role_name,
            "user_status": user_status_out,
            "is_active": user.is_active,
            "is_deleted": getattr(user, 'is_deleted', False),
            "is_email_verified": user.is_email_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "invitation_id": str(invitation.id) if invitation else None,
            "invitation_status": inv_status_out,
            "main_invite_status": invitation.status.value if invitation else None,
            "invitation_expires_at": invitation.expires_at.isoformat() if invitation else None
        }


def get_users_with_invitation_details(
    organization_id: str = None,
    business_id: str = None,
    invitation_status_list: List[str] = None,
    user_status_list: List[str] = None,
    role_list: List[str] = None,
    search: str = None,
    page: int = 1,
    limit: int = 10
) -> dict:
    """
    Get users with invitation details and filtering options
    - If invitation_status is provided: Only show users with invitations matching those statuses
    - If user_status is provided: Filter users by active/inactive status
    - If both are provided: Apply both filters (AND condition)
    - If neither is provided: Show all users with invitations
    """
    session = ScopedSession()
    try:
        # Initialize helper classes
        query_builder = UserInvitationQueryBuilder(session)
        data_processor = UserInvitationDataProcessor(session)
        
        # Build query with filters
        query = query_builder.build_base_query(invitation_status_list)
        query = query_builder.apply_organization_filters(query, organization_id, business_id)
        query = query_builder.apply_invitation_status_filters(query, invitation_status_list)
        query = query_builder.apply_user_status_filters(query, user_status_list)
        query = query_builder.apply_role_filters(query, role_list)
        query = query_builder.apply_search_filters(query, search)
        
        # Apply distinct, ordering, and pagination
        # Use distinct() without column specification to avoid DISTINCT ON conflict
        query = query.distinct()
        query = query.order_by(Users.created_at.desc())
        total_count = query.count()
        offset = (page - 1) * limit
        users = query.offset(offset).limit(limit).all()
        
        # Process user data
        users_data = [data_processor.process_user_data(user) for user in users]
        
        return {
            "users": users_data,
            "pagination": {
                "total": total_count,
                "page": page,
                "limit": limit,
                "has_more": offset + limit < total_count
            },
            "filters_applied": {
                "organization_id": organization_id,
                "business_id": business_id,
                "invitation_status_filter": invitation_status_list,
                "user_status_filter": user_status_list,
                "role_filter": role_list,
                "search": search
            }
        }

    except Exception as e:
        logger.error(f"Error getting users with invitation details: {e}")
        return {
            "users": [],
            "pagination": {"total": 0, "page": page, "limit": limit, "has_more": False},
            "filters_applied": {},
            "error": str(e)
        }
    finally:
        session.close()
        ScopedSession.remove()


def delete_user_by_email(email: str) -> dict:
    """
    Delete user with different logic based on status:
    - If user is not confirmed (invitation pending/expired): Hard delete from database
    - If user is active: Soft delete (set is_deleted = True)

    Args:
        email: Email address of user to delete

    Returns:
        Dict with success status, message, and data
    """
    session = ScopedSession()
    try:
        # Check if user exists
        
        user = (
            session.query(Users)
            .options(joinedload(Users.profile))
            .filter(Users.email == email)
            .first()
        )

        if not user:
            deleted_invitations = session.query(UserInvitation).filter(
                UserInvitation.email == email
            ).delete()
            session.commit()
            return {
                "success": True,
                "message": f"No user found. Deleted {deleted_invitations} invitations (if any).",
                "data": {
                    "email": email,
                    "user_deleted": False,
                    "invitations_deleted": deleted_invitations
                }
            }

        # Check user status to determine deletion type
        is_active_user = user.is_active and user.is_email_verified

        # Check for pending invitations
        pending_invitation = session.query(UserInvitation).filter(
            UserInvitation.email == email,
            UserInvitation.status.in_([
                InvitationStatusEnum.PENDING,
                InvitationStatusEnum.EXPIRED
            ])
        ).first()

        if is_active_user:
            user.is_active = False
            user.is_deleted = True
            if user.profile:
                user.profile.is_active = False
            try:
                cognito_username = get_cognito_username_by_user_id(user.user_id)
                update_cognito_user_attributes(cognito_username, {'is_active': False})
                logger.info(f"Disabled user {email} in Cognito as part of deletion")
            except Exception as e:
                logger.warning(f"Failed to disable user {email} in Cognito: {e}")

            session.commit()
            return {
                "success": True,
                "message": "Active user found",
                "data": {
                    "email": email,
                    "deletion_type": "invitation_only",
                    "user_was_active": True
                }
            }
        
        if user.is_deleted:
            return {
                "success": False,
                "message": f"User {email} is already deactivated",
                "data": {
                    "email": email,
                    "already_soft_deleted": True
                }
            }

        if pending_invitation:
            # Hard delete
            if user.profile:
                session.delete(user.profile)

            session.query(UserInvitation).filter(
                UserInvitation.email == email
            ).delete()

            session.delete(user)

            cognito_deleted = False
            try:
                delete_cognito_user(email)
                cognito_deleted = True
                logger.info(f"Deleted user {email} from Cognito")
            except Exception as e:
                logger.warning(f"Failed to delete user {email} from Cognito: {e}")

            session.commit()
            return {
                "success": True,
                "message": f"User {email} permanently deleted (unconfirmed user)",
                "data": {
                    "email": email,
                    "deletion_type": "hard_delete",
                    "user_was_active": False,
                    "had_pending_invitation": pending_invitation is not None,
                    "cognito_deleted": cognito_deleted
                }
            }

        else:
            return {
                "success": False,
                "message": f"No matching deletion condition for {email}",
                "error_code": NOT_FOUND
            }

    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting user {email}: {e}")
        return {
            "success": False,
            "message": f"Failed to delete user: {str(e)}",
            "error_code": SOMETHING_WENT_WRONG
        }
    finally:
        session.close()
        ScopedSession.remove()


def activate_user_and_update_password(email: str, new_password: str) -> bool:
    """
    Activate user and update password after invitation acceptance

    Args:
        email: User email address
        new_password: New password to hash and store

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        user = session.query(Users).filter(Users.email == email).first()
        if not user:
            logger.error(f"User not found for email: {email}")
            return False

        # Hash the new password
        hashed_password = generate_hash(new_password)

        # Activate user and update password
        user.is_active = True
        user.is_email_verified = True
        user.password = hashed_password
        user.updated_at = datetime.now(timezone.utc)

        # Activate user profile as well
        if user.profile:
            user.profile.is_active = True
            user.profile.updated_at = datetime.now(timezone.utc)

        session.commit()
        logger.info(f"User {email} activated and password updated")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error activating user and updating password for {email}: {e}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def update_user_password(email: str, new_password: str) -> bool:
    """
    Update user password in database

    Args:
        email: User email address
        new_password: New password to hash and store

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        user = session.query(Users).filter(Users.email == email).first()
        if not user:
            logger.error(f"User not found for email: {email}")
            return False

        # Hash the new password
        hashed_password = generate_hash(new_password)

        # Update password
        user.password = hashed_password
        user.updated_at = datetime.now(timezone.utc)

        session.commit()
        logger.info(f"Password updated for user {email}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating password for {email}: {e}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def send_invitation_email_helper(
    email: str, 
    organization_id: str = None, 
    role_name: str = None, 
    invitation_token: str = None, 
    user_name: str = None
) -> dict:
    """
    Helper function to send invitation email with organization lookup
    
    Args:
        email: Recipient email address
        organization_id: Organization ID (optional)
        role_name: Role name for the invitation
        invitation_token: Invitation token
        user_name: User name (optional)
    
    Returns:
        Dict with email sending result
    """
    session = ScopedSession()
    try:
        # Get organization name if organization_id provided
        org_name = "Organization"  # Default fallback
        if organization_id:
            org = get_organization_by_id(str(organization_id))
            if org:
                org_name = org.name

        # Send invitation email
        return send_invitation_email(
            recipient_email=email,
            organization_name=org_name or "Inspire Genius",
            role_name=role_name or "Member",
            invitation_token=invitation_token,
            user_name=user_name
        )
    finally:
        session.close()
        ScopedSession.remove()


def check_existing_invitation(email: str) -> Dict[str, Any]:
    """
    Check for existing invitations and return appropriate response
    
    Args:
        email: Email address to check
        
    Returns:
        Dict with should_block (bool) and response data if blocking
    """
    session = ScopedSession()
    try:
        existing_invitation = session.query(UserInvitation).filter(
            UserInvitation.email == email
        ).order_by(UserInvitation.invited_at.desc()).first()

        if not existing_invitation:
            return {"should_block": False}

        if existing_invitation.status == InvitationStatusEnum.PENDING:
            # Check if invitation is expired
            current_time = datetime.now(timezone.utc)
            expires_at = existing_invitation.expires_at.replace(tzinfo=timezone.utc) if existing_invitation.expires_at.tzinfo is None else existing_invitation.expires_at
            
            if current_time > expires_at:
                # Update expired invitation status
                update_invitation_status(existing_invitation.id, InvitationStatusEnum.EXPIRED)
                return {
                    "should_block": True,
                    "message": "Previous invitation has expired. Please use the resend invitation option to send a new invitation.",
                    "error_code": "VALIDATION_ERROR_CODE",
                    "data": {
                        "invitation_id": str(existing_invitation.id),
                        "status": "expired",
                        "email": email,
                        "action_required": "resend_invitation"
                    }
                }
            else:
                # Active pending invitation exists
                return {
                    "should_block": True,
                    "message": "User has already been invited and invitation is still pending. Please wait for user to accept or use resend invitation option.",
                    "error_code": "VALIDATION_ERROR_CODE",
                    "data": {
                        "invitation_id": str(existing_invitation.id),
                        "status": "pending",
                        "email": email,
                        "expires_at": expires_at.isoformat(),
                        "action_required": "wait_or_resend"
                    }
                }
        elif existing_invitation.status == InvitationStatusEnum.EXPIRED:
            return {
                "should_block": True,
                "message": "Previous invitation has expired. Please use the resend invitation option to send a new invitation.",
                "error_code": "VALIDATION_ERROR_CODE",
                "data": {
                    "invitation_id": str(existing_invitation.id),
                    "status": "expired",
                    "email": email,
                    "action_required": "resend_invitation"
                }
            }
        elif existing_invitation.status == InvitationStatusEnum.ACCEPTED:
            return {
                "should_block": True,
                "message": "User has already accepted the invitation and account is active.",
                "error_code": "VALIDATION_ERROR_CODE",
                "data": {
                    "invitation_id": str(existing_invitation.id),
                    "status": "accepted",
                    "email": email,
                    "action_required": "user_already_exists"
                }
            }

        # For CANCELLED status, don't block
        return {"should_block": False}

    except Exception as e:
        logger.error(f"Error checking existing invitation for {email}: {e}")
        return {"should_block": False}
    finally:
        session.close()
        ScopedSession.remove()


class UserEditValidator:
    """Helper class for user edit operations validation and processing"""
    
    def __init__(self, session):
        self.session = session
    
    def validate_user_exists(self, email: str) -> tuple[Users, dict]:
        """Validate user exists and return user or error response"""
        user = self.session.query(Users).options(joinedload(Users.profile)).filter(Users.email == email).first()
        if not user:
            return None, {"success": False, "message": "User not found", "error_code": NOT_FOUND}
        return user, None
    
    def validate_invitation_status(self, email: str) -> Optional[dict]:
        """Validate user invitation status allows editing"""
        invitation = self.session.query(UserInvitation).filter(UserInvitation.email == email).first()
        if invitation and invitation.status.value != "accepted":
            return {"success": False, "message": f"Cannot edit user with invitation status: {invitation.status.value}"}
        return None
    
    def process_name_update(
        self, user: Users, edit_data: dict,
        updated: list, cognito_attributes: dict
    ):
        """Process name field update (first_name and last_name)"""
        if user.profile:
            name_updated = False
            if edit_data.get('first_name'):
                user.profile.first_name = edit_data['first_name']
                name_updated = True

            if edit_data.get('last_name'):
                user.profile.last_name = edit_data['last_name']
                name_updated = True

            if name_updated:
                updated.append('name')
                # Update Cognito with combined full name
                full_name = f"{user.profile.first_name or ''} {user.profile.last_name or ''}".strip()
                if full_name:
                    cognito_attributes['name'] = full_name
    
    def process_status_update(self, user: Users, edit_data: dict, updated: list, cognito_attributes: dict):
        """Process status field update"""
        if 'is_active' in edit_data:
            user.is_active = edit_data['is_active']
            if user.profile:
                user.profile.is_active = user.is_active
            user.is_deleted = not user.is_active
            updated.append('status')
            cognito_attributes['is_active'] = edit_data['is_active']
    
    def process_role_update(
        self, user: Users, edit_data: dict, updated: list, cognito_attributes: dict
    ) -> Optional[dict]:
        """Process role field update"""
        if edit_data.get('role_id'):
            user.role_id = edit_data['role_id']
            updated.append('role')
            role = get_role_by_id(edit_data["role_id"])
            if not role:
                return {"success": False, "message": "Role not found"}
            cognito_attributes['custom:role'] = role.name
        return None
    
    def update_cognito_user(self, user_id: str, cognito_attributes: dict) -> Optional[dict]:
        """Update user in Cognito"""
        cognito_username = get_cognito_username_by_user_id(user_id)
        cognito_response = update_cognito_user_attributes(
            username=cognito_username, 
            attributes=cognito_attributes
        )
        if not cognito_response['status']:
            return {
                "success": False,
                "message": f"User updated in DB but failed in Cognito: {cognito_response['message']}"
            }
        return None


def edit_active_user(email: str, edit_data: dict) -> dict:
    """Edit active user - blocks if user has any invitation status"""
    session = ScopedSession()
    try:
        validator = UserEditValidator(session)
        
        # Validate user exists
        user, error_response = validator.validate_user_exists(email)
        if error_response:
            return error_response
        
        # Validate invitation status
        error_response = validator.validate_invitation_status(email)
        if error_response:
            return error_response

        # Process field updates
        updated = []
        cognito_attributes = {}
        
        validator.process_name_update(user, edit_data, updated, cognito_attributes)
        validator.process_status_update(user, edit_data, updated, cognito_attributes)
        
        error_response = validator.process_role_update(user, edit_data, updated, cognito_attributes)
        if error_response:
            return error_response

        # Apply updates if any fields were changed
        if not updated:
            return {"success": False, "message": "No fields to update"}
        
        # Save to database
        session.add(user)
        if user.profile:
            session.add(user.profile)

        # Update Cognito
        error_response = validator.update_cognito_user(user.user_id, cognito_attributes)
        if error_response:
            return error_response
            
        session.commit()
        return {
            "success": True,
            "message": "User updated",
            "data": {"updated_fields": updated}
        }
        
    except Exception as e:
        session.rollback()
        return {"success": False, "message": str(e)}
    finally:
        session.close()
        ScopedSession.remove()
