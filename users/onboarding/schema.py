import uuid
from typing import Optional, Dict, Any
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from users.models.user import UserProfile, Users
from users.models.rbac import Roles
from users.aws_wrapper.cognito_utils import (
    get_cognito_username_by_user_id,
    update_cognito_user_attributes,
)
from users.auth_service.utils import get_full_name


def create_user_profile(
    user_id: str,
    first_name: str,
    last_name: str,
    date_of_birth: Optional[str] = None,
    additional_info: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update user profile during onboarding

    Args:
        user_id: User's UUID
        first_name: User's first name
        last_name: User's last name
        date_of_birth: User's date of birth (optional)
        additional_info: Additional information about the user (optional)

    Returns:
        Dict containing status, message, and profile data
    """
    session = ScopedSession()
    try:
        # Check if user exists
        user = session.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return {
                "status": False,
                "message": "User not found",
                "error_type": "not_found"
            }

        # Check if profile already exists - if yes, update it
        if user.profile:
            profile = user.profile
            profile.first_name = first_name
            profile.last_name = last_name
            profile.date_of_birth = date_of_birth
            profile.additional_info = additional_info
            profile.is_profile_complete = True

            message = "Profile updated successfully"
            logger.info(f"User profile updated for user_id: {user_id}")
        else:
            # Create new profile
            profile = UserProfile(
                id=uuid.uuid4(),
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth,
                additional_info=additional_info,
                is_profile_complete=True,
            )
            session.add(profile)
            message = "Profile created successfully"
            logger.info(f"User profile created for user_id: {user_id}")

        session.commit()

        # Update Cognito with the full name
        full_name = get_full_name(first_name, last_name)
        cognito_username = get_cognito_username_by_user_id(user_id)
        if cognito_username:
            cognito_response = update_cognito_user_attributes(
                username=cognito_username,
                attributes={
                    "name": full_name,
                    "custom:is_onboarded": "true"
                }
            )
            if not cognito_response.get("status"):
                logger.warning(
                    f"Profile saved but Cognito update failed: {cognito_response.get('message')}"
                )

        return {
            "status": True,
            "message": message,
            "profile": {
                "profile_id": str(profile.id),
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "full_name": profile.full_name,
                "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                "role_id": str(profile.role) if profile.role else None,
                "additional_info": profile.additional_info,
            }
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating/updating user profile: {str(e)}")
        return {
            "status": False,
            "message": f"Failed to save profile: {str(e)}",
            "error_type": "server_error"
        }
    finally:
        session.close()


def update_user_profile(
    user_id: str,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    additional_info: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update user profile

    Args:
        user_id: User's UUID
        first_name: User's first name (optional)
        last_name: User's last name (optional)
        role_id: Role UUID (optional)
        date_of_birth: User's date of birth (optional)
        additional_info: Additional information (optional)

    Returns:
        Dict containing status, message, and updated profile data
    """
    session = ScopedSession()
    try:
        # Get user profile
        user = session.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return {
                "status": False,
                "message": "User not found",
                "error_type": "not_found"
            }

        if not user.profile:
            return {
                "status": False,
                "message": "User profile not found. Please complete onboarding first.",
                "error_type": "not_found"
            }

        profile = user.profile
        updated_fields = []
        cognito_attributes = {}

        # Update fields if provided
        if first_name is not None:
            profile.first_name = first_name
            updated_fields.append("first_name")

        if last_name is not None:
            profile.last_name = last_name
            updated_fields.append("last_name")

        # Update Cognito name if either first_name or last_name changed
        if first_name is not None or last_name is not None:
            full_name = get_full_name(profile.first_name, profile.last_name)
            if full_name:
                cognito_attributes["name"] = full_name

        if date_of_birth is not None:
            profile.date_of_birth = date_of_birth
            updated_fields.append("date_of_birth")

        if additional_info is not None:
            profile.additional_info = additional_info
            updated_fields.append("additional_info")

        if not updated_fields:
            return {
                "status": False,
                "message": "No fields to update",
                "error_type": "validation_error"
            }

        session.commit()

        # Update Cognito if needed
        if cognito_attributes:
            cognito_username = get_cognito_username_by_user_id(user_id)
            if cognito_username:
                cognito_response = update_cognito_user_attributes(
                    username=cognito_username,
                    attributes=cognito_attributes
                )
                if not cognito_response.get("status"):
                    logger.warning(
                        f"Profile updated but Cognito update failed: {cognito_response.get('message')}"
                    )

        logger.info(f"User profile updated successfully for user_id: {user_id}")

        # Get updated role name
        role = session.query(Roles).filter(Roles.id == profile.role).first()

        return {
            "status": True,
            "message": f"Profile updated successfully. Updated fields: {', '.join(updated_fields)}",
            "profile": {
                "profile_id": str(profile.id),
                "first_name": profile.first_name,
                "last_name": profile.last_name,
                "full_name": profile.full_name,
                "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
                "additional_info": profile.additional_info,
            }
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating user profile: {str(e)}")
        return {
            "status": False,
            "message": f"Failed to update profile: {str(e)}",
            "error_type": "server_error"
        }
    finally:
        session.close()