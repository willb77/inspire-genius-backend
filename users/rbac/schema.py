from typing import Any, Dict, Optional, List
import uuid
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy import and_
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from users.models.rbac import (
    Roles, Groups,
    Permissions,
    RolePermission,
    GroupPermission
)
from users.models.user import UserProfile, Users


# Role CRUD Operations
def get_role_id(name: str, create_if_missing: bool = False) -> Optional[str]:
    """
    Get the role ID by name, optionally creating the role if not found.

    Args:
        name: Role name to search for.
        create_if_missing: If True, creates the role when not found.

    Returns:
        Role ID as a string if found or created, None otherwise.
    """
    session = ScopedSession()
    try:
        if not name:
            return None

        # Case-insensitive match on role name
        role_id = session.query(Roles.id).filter(
            func.lower(Roles.name) == name.lower()
        ).scalar()

        if role_id:
            return str(role_id)

        # If role not found and creation is allowed
        if create_if_missing:
            role_data = {"name": name}
            return create_role(role_data)  # Should return the new role's ID

    except Exception as e:
        logger.exception("Failed to get or create role", exc_info=e)
    finally:
        session.close()

    return None


def create_role(data):
    """
    Function to create a new role
    :param data: Role data
    :return: Role ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        role_id = uuid.uuid4()
        role = Roles(
            id=role_id,
            name=data["name"],
            is_deleted=False
        )
        session.add(role)
        session.commit()
        return role_id
    except Exception as e:
        logger.error(f"Failed to create role: {e}")
        session.rollback()
    finally:
        session.close()
    return None


def get_all_roles():
    """
    Function to get all roles
    :return: List of roles
    """
    session = ScopedSession()
    try:
        roles = session.query(Roles).filter(
            Roles.is_deleted.is_(False)
        ).all()
        return roles
    except Exception as e:
        logger.error(f"Failed to get roles: {e}")
    finally:
        session.close()
    return []


def get_role_by_id(role_id):
    """
    Function to get a role by ID
    :param role_id: Role ID
    :return: Role if found, None otherwise
    """
    session = ScopedSession()
    try:
        role = session.query(Roles).filter(
            and_(
                Roles.id == role_id,
                Roles.is_deleted.is_(False)
            )
        ).first()
        return role
    except Exception as e:
        logger.error(f"Failed to get role: {e}")
    finally:
        session.close()
    return None


def update_role(role_id, data):
    """
    Function to update a role
    :param role_id: Role ID
    :param data: Updated role data
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        role = session.query(Roles).filter(
            and_(
                Roles.id == role_id,
                Roles.is_deleted.is_(False)
            )
        ).first()

        if not role:
            return False

        # Update role fields
        if "name" in data:
            role.name = data["name"]

        role.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update role: {e}")
        session.rollback()
    finally:
        session.close()
    return False


def delete_role(role_id):
    """
    Function to soft delete a role
    :param role_id: Role ID
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        role = session.query(Roles).filter(
            and_(
                Roles.id == role_id,
                Roles.is_deleted.is_(False)
            )
        ).first()

        if not role:
            return False

        # Soft delete the role
        role.is_deleted = True
        role.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete role: {e}")
        session.rollback()
    finally:
        session.close()
    return False


# Group CRUD Operations
def get_group_id(name):
    """
    Function to get group id by name
    :param name:
    :return:
    """
    session = ScopedSession()
    try:
        group_id = session.query(Groups.id).filter(
            func.lower(Groups.name) == name.lower()
        )
        if group_id:
            return group_id.scalar()
    except Exception as e:
        logger.exception("Failed to get group id: ", exc_info=e)
    finally:
        session.close()
    return None


def create_group(data):
    """
    Function to create a new group
    :param data: Group data
    :return: Group ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        group_id = uuid.uuid4()
        group = Groups(
            id=group_id,
            name=data["name"],
            is_deleted=False
        )
        session.add(group)
        session.commit()
        return group_id
    except Exception as e:
        logger.error(f"Failed to create group: {e}")
        session.rollback()
    finally:
        session.close()
    return None


def get_all_groups():
    """
    Function to get all groups
    :return: List of groups
    """
    session = ScopedSession()
    try:
        groups = session.query(Groups).filter(
            Groups.is_deleted.is_(False)
        ).all()
        return groups
    except Exception as e:
        logger.error(f"Failed to get groups: {e}")
    finally:
        session.close()
    return []


def get_group_by_id(group_id):
    """
    Function to get a group by ID
    :param group_id: Group ID
    :return: Group if found, None otherwise
    """
    session = ScopedSession()
    try:
        group = session.query(Groups).filter(
            and_(
                Groups.id == group_id,
                Groups.is_deleted.is_(False)
            )
        ).first()
        return group
    except Exception as e:
        logger.error(f"Failed to get group: {e}")
    finally:
        session.close()
    return None


def update_group(group_id, data):
    """
    Function to update a group
    :param group_id: Group ID
    :param data: Updated group data
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        group = session.query(Groups).filter(
            and_(
                Groups.id == group_id,
                Groups.is_deleted.is_(False)
            )
        ).first()

        if not group:
            return False

        # Update group fields
        if "name" in data:
            group.name = data["name"]

        group.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update group: {e}")
        session.rollback()
    finally:
        session.close()
    return False


def delete_group(group_id):
    """
    Function to soft delete a group
    :param group_id: Group ID
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        group = session.query(Groups).filter(
            and_(
                Groups.id == group_id,
                Groups.is_deleted.is_(False)
            )
        ).first()

        if not group:
            return False

        # Soft delete the group
        group.is_deleted = True
        group.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete group: {e}")
        session.rollback()
    finally:
        session.close()
    return False


# Permission CRUD Operations
def get_permission_id(name):
    """
    Function to get permission id by name
    :param name:
    :return:
    """
    session = ScopedSession()
    try:
        permission_id = session.query(Permissions.id).filter(
            func.lower(Permissions.name) == name.lower()
        )
        if permission_id:
            return permission_id.scalar()
    except Exception as e:
        logger.exception("Failed to get permission id: ", exc_info=e)
    finally:
        session.close()
    return None


def create_permission(data):
    """
    Function to create a new permission
    :param data: Permission data
    :return: Permission ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        permission_id = uuid.uuid4()
        permission = Permissions(
            id=permission_id,
            name=data["name"],
            created_by=data.get("created_by"),
            is_deleted=False
        )
        session.add(permission)
        session.commit()
        return permission_id
    except Exception as e:
        logger.error(f"Failed to create permission: {e}")
        session.rollback()
    finally:
        session.close()
    return None


def get_all_permissions():
    """
    Function to get all permissions
    :return: List of permissions
    """
    session = ScopedSession()
    try:
        permissions = session.query(Permissions).filter(
            Permissions.is_deleted.is_(False)
        ).all()
        return permissions
    except Exception as e:
        logger.error(f"Failed to get permissions: {e}")
    finally:
        session.close()
    return []


def get_permission_by_id(permission_id):
    """
    Function to get a permission by ID
    :param permission_id: Permission ID
    :return: Permission if found, None otherwise
    """
    session = ScopedSession()
    try:
        permission = session.query(Permissions).filter(
            and_(
                Permissions.id == permission_id,
                Permissions.is_deleted.is_(False)
            )
        ).first()
        return permission
    except Exception as e:
        logger.error(f"Failed to get permission: {e}")
    finally:
        session.close()
    return None


def update_permission(permission_id, data):
    """
    Function to update a permission
    :param permission_id: Permission ID
    :param data: Updated permission data
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        permission = session.query(Permissions).filter(
            and_(
                Permissions.id == permission_id,
                Permissions.is_deleted.is_(False)
            )
        ).first()

        if not permission:
            return False

        # Update permission fields
        if "name" in data:
            permission.name = data["name"]

        permission.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update permission: {e}")
        session.rollback()
    finally:
        session.close()
    return False


def delete_permission(permission_id):
    """
    Function to soft delete a permission
    :param permission_id: Permission ID
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        permission = session.query(Permissions).filter(
            and_(
                Permissions.id == permission_id,
                Permissions.is_deleted.is_(False)
            )
        ).first()

        if not permission:
            return False

        # Soft delete the permission
        permission.is_deleted = True
        permission.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to delete permission: {e}")
        session.rollback()
    finally:
        session.close()
    return False


# Role-Permission Operations
def assign_permission_to_role(role_id, permission_id, created_by):
    """
    Function to assign a permission to a role
    :param role_id: Role ID
    :param permission_id: Permission ID
    :param created_by: User ID who created this assignment
    :return: Assignment ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Check if the assignment already exists
        existing = session.query(RolePermission).filter(
            and_(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
                RolePermission.is_deleted.is_(False)
            )
        ).first()

        if existing:
            return existing.id

        assignment_id = uuid.uuid4()
        role_permission = RolePermission(
            id=assignment_id,
            role_id=role_id,
            permission_id=permission_id,
            created_by=created_by,
            is_deleted=False
        )
        session.add(role_permission)
        session.commit()
        return assignment_id
    except Exception as e:
        logger.error(f"Failed to assign permission to role: {e}")
        session.rollback()
    finally:
        session.close()
    return None


def remove_permission_from_role(role_id, permission_id):
    """
    Function to remove a permission from a role
    :param role_id: Role ID
    :param permission_id: Permission ID
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        role_permission = session.query(RolePermission).filter(
            and_(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
                RolePermission.is_deleted.is_(False)
            )
        ).first()

        if not role_permission:
            return False

        # Soft delete the assignment
        role_permission.is_deleted = True
        role_permission.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to remove permission from role: {e}")
        session.rollback()
    finally:
        session.close()
    return False


def get_role_permissions(role_id):
    """
    Function to get all permissions assigned to a role
    :param role_id: Role ID
    :return: List of permissions
    """
    session = ScopedSession()
    try:
        permissions = session.query(Permissions).join(
            RolePermission,
            and_(
                RolePermission.permission_id == Permissions.id,
                RolePermission.role_id == role_id,
                RolePermission.is_deleted.is_(False),
                Permissions.is_deleted.is_(False)
            )
        ).all()
        return permissions
    except Exception as e:
        logger.error(f"Failed to get role permissions: {e}")
    finally:
        session.close()
    return []


# Group-Permission Operations
def assign_permission_to_group(group_id, permission_id, created_by):
    """
    Function to assign a permission to a group
    :param group_id: Group ID
    :param permission_id: Permission ID
    :param created_by: User ID who created this assignment
    :return: Assignment ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Check if the assignment already exists
        existing = session.query(GroupPermission).filter(
            and_(
                GroupPermission.group_id == group_id,
                GroupPermission.permission_id == permission_id,
                GroupPermission.is_deleted.is_(False)
            )
        ).first()

        if existing:
            return existing.id

        assignment_id = uuid.uuid4()
        group_permission = GroupPermission(
            id=assignment_id,
            group_id=group_id,
            permission_id=permission_id,
            created_by=created_by,
            is_deleted=False
        )
        session.add(group_permission)
        session.commit()
        return assignment_id
    except Exception as e:
        logger.error(f"Failed to assign permission to group: {e}")
        session.rollback()
    finally:
        session.close()
    return None


def remove_permission_from_group(group_id, permission_id):
    """
    Function to remove a permission from a group
    :param group_id: Group ID
    :param permission_id: Permission ID
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        group_permission = session.query(GroupPermission).filter(
            and_(
                GroupPermission.group_id == group_id,
                GroupPermission.permission_id == permission_id,
                GroupPermission.is_deleted.is_(False)
            )
        ).first()

        if not group_permission:
            return False

        # Soft delete the assignment
        group_permission.is_deleted = True
        group_permission.updated_at = datetime.now()
        session.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to remove permission from group: {e}")
        session.rollback()
    finally:
        session.close()
    return False


def get_group_permissions(group_id):
    """
    Function to get all permissions assigned to a group
    :param group_id: Group ID
    :return: List of permissions
    """
    session = ScopedSession()
    try:
        permissions = session.query(Permissions).join(
            GroupPermission,
            and_(
                GroupPermission.permission_id == Permissions.id,
                GroupPermission.group_id == group_id,
                GroupPermission.is_deleted.is_(False),
                Permissions.is_deleted.is_(False)
            )
        ).all()
        return permissions
    except Exception as e:
        logger.error(f"Failed to get group permissions: {e}")
    finally:
        session.close()
    return []


def add_user_to_group(user_id, group_name: str) -> bool:
    """
    Assign a user to a group. Creates the group if it doesn't exist.

    :param user_id: UUID of the user
    :param group_name: Name of the group
    :return: True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        # Check if the group exists
        group = session.query(Groups).filter_by(
            name=group_name, is_deleted=False
        ).first()

        # Create group if not exists
        if not group:
            group_id = create_group({"name": group_name})
            if not group_id:
                return False
            group = session.query(Groups).get(group_id)

        # Get user's profile
        user_profile = session.query(UserProfile).filter_by(
            user_id=user_id
        ).first()
        if not user_profile:
            # If user doesn't have a profile yet, create one
            user_profile = UserProfile(
                id=uuid.uuid4(),
                user_id=user_id,
                user_group=group.id
            )
            session.add(user_profile)
        else:
            # If profile exists, just update the group
            user_profile.user_group = group.id

        session.commit()
        logger.info(f"Assigned user {user_id} to group '{group_name}'")
        return True

    except Exception as e:
        logger.exception(
            f"Failed to assign user {user_id} to group '{group_name}': {e}"
        )
        session.rollback()
        return False
    finally:
        session.close()

def get_user_role_info(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user's role information including organization and business context
    
    Args:
        user_id: User ID
        
    Returns:
        Dictionary with role info or None
    """
    session = ScopedSession()
    try:
        user_profile = session.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        if not user_profile:
            return None
        
        role_info = {
            "user_id": user_id,
            "role_id": str(user_profile.role) if user_profile.role else None,
            "organization_id": str(user_profile.org_id) if user_profile.org_id else None,
            "business_id": str(user_profile.business_id) if user_profile.business_id else None,
            "is_primary": user_profile.is_primary,
            "is_active": user_profile.is_active
        }
        
        # Get role details
        if user_profile.role:
            role = session.query(Roles).filter(Roles.id == user_profile.role).first()
            if role:
                role_info.update({
                    "role_name": role.name,
                    "role_level": role.role_level
                })
        
        return role_info

    except Exception as e:
        logger.error(f"Error getting user role info: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_super_admin_emails() -> List[str]:
    """
    Get all super admin user emails for notifications

    Returns:
        List of super admin email addresses
    """
    session = ScopedSession()
    try:
        # Get the super-admin role
        super_admin_role = session.query(Roles).filter(
            func.lower(Roles.name) == "super-admin"
        ).first()

        if not super_admin_role:
            logger.warning("Super-admin role not found")
            return []

        # Get all user profiles with super-admin role
        super_admin_profiles = session.query(UserProfile).filter(
            UserProfile.role == super_admin_role.id
        ).all()

        # Get emails from the Users table
        emails = []
        for profile in super_admin_profiles:
            user = session.query(Users).filter(
                Users.user_id == profile.user_id
            ).first()
            if user and user.email:
                emails.append(user.email)

        logger.info(f"Found {len(emails)} super admin email(s)")
        return emails

    except Exception as e:
        logger.error(f"Error getting super admin emails: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()

