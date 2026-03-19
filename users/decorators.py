from typing import List
from fastapi import Depends, HTTPException
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.rbac.schema import get_user_role_info

# Canonical list of valid role names across the system
VALID_ROLES = {"user", "super-admin", "coach-admin", "org-admin", "prompt-engineer", "admin"}


def require_role(*allowed_roles: str):
    """
    Flexible role-based access control decorator.

    Equivalent to createRoleGuard(...allowedRoles) — accepts one or more
    role name strings and returns a FastAPI dependency that enforces them.

    Usage:
        @router.get("/endpoint")
        def my_endpoint(user_data: dict = Depends(require_role("super-admin", "org-admin"))):
            ...

    Args:
        *allowed_roles: Role names that are permitted access

    Returns:
        FastAPI dependency function that returns user_data dict with role info

    Raises:
        HTTPException: 401 for auth issues, 403 for access denied, 500 for server errors
    """
    allowed_set = {r.lower() for r in allowed_roles}

    def dependency(user_data: dict = Depends(verify_token)):
        try:
            user_id = user_data.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required"
                )

            # Magic Auth tokens carry role in JWT claims — skip DB lookup
            if user_data.get("_auth_source") == "magic_auth":
                user_role = (user_data.get("user_role") or "user").lower()
                if user_role not in allowed_set:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Access denied - requires one of {sorted(allowed_set)}, current role: {user_role}"
                    )
                user_data["role_info"] = {
                    "user_id": user_id,
                    "role_name": user_role,
                    "organization_id": None,
                    "business_id": None,
                    "is_primary": True,
                    "is_active": True,
                }
                user_data["user_role"] = user_role
                return user_data

            # Cognito / DB path
            user_role_info = get_user_role_info(user_id)
            if not user_role_info:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied - no role information found"
                )

            user_role = user_role_info.get("role_name", "").lower()

            if user_role not in allowed_set:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied - requires one of {sorted(allowed_set)}, current role: {user_role}"
                )

            user_data["role_info"] = user_role_info
            user_data["user_role"] = user_role
            return user_data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in role checking: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during role verification"
            )

    return dependency


def require_authenticated_user():
    """
    Simple authentication decorator - allows any authenticated user
    
    This decorator only verifies that the user has a valid JWT token.
    It does not perform any role-based authorization checks.
    
    Returns:
        FastAPI dependency function that returns user_data dict
        
    Raises:
        HTTPException: 401 if authentication fails, 500 for server errors
    """
    def dependency(user_data: dict = Depends(verify_token)):
        try:
            user_id = user_data.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required - invalid user token"
                )
            return user_data
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in authentication: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during authentication"
            )
    return dependency


def require_admin_role():
    """
    Role-based access control decorator for admin and super-admin roles
    
    This decorator ensures that only users with 'admin' or 'super-admin' roles
    can access the protected endpoint. Admin users are automatically scoped
    to their organization, while super-admin users have system-wide access.
    
    Returns:
       function that returns user_data dict with role info
        
    Raises:
        HTTPException: 401 for auth issues, 403 for access denied, 500 for server errors
    """
    def dependency(user_data: dict = Depends(verify_token)):
        try:
            user_id = user_data.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required"
                )

            # Magic Auth tokens carry role in JWT claims — skip DB lookup
            if user_data.get("_auth_source") == "magic_auth":
                user_role = (user_data.get("user_role") or "user").lower()
                allowed_roles = ["admin", "super-admin"]
                if user_role not in allowed_roles:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Access denied - requires admin or super-admin role, current role: {user_role}"
                    )
                user_data["role_info"] = {
                    "user_id": user_id,
                    "role_name": user_role,
                    "organization_id": None,
                    "business_id": None,
                    "is_primary": True,
                    "is_active": True,
                }
                user_data["user_role"] = user_role
                return user_data

            # Get user role information
            user_role_info = get_user_role_info(user_id)
            if not user_role_info:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied - no role information found"
                )

            user_role = user_role_info.get("role_name", "").lower()

            # Allow access only for admin and super-admin roles
            allowed_roles = ["admin", "super-admin"]

            if user_role not in allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied - requires admin or super-admin role, current role: {user_role}"
                )

            # Add role information to user_data for use in endpoints
            user_data["role_info"] = user_role_info
            user_data["user_role"] = user_role

            return user_data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in role checking: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during role verification"
            )

    return dependency


def require_super_admin_role():
    """
    Role-based access control decorator for super-admin role only

    This decorator ensures that only users with 'super-admin' role
    can access the protected endpoint. This is for system-level operations
    that should not be accessible to organization admins.

    Returns:
        FastAPI dependency function that returns user_data dict with role info

    Raises:
        HTTPException: 401 for auth issues, 403 for access denied, 500 for server errors
    """
    def dependency(user_data: dict = Depends(verify_token)):
        try:
            user_id = user_data.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required"
                )

            # Magic Auth tokens carry role in JWT claims — skip DB lookup
            if user_data.get("_auth_source") == "magic_auth":
                user_role = (user_data.get("user_role") or "user").lower()
                if user_role != "super-admin":
                    raise HTTPException(
                        status_code=403,
                        detail=f"Access denied - requires super-admin role, current role: {user_role}"
                    )
                user_data["role_info"] = {
                    "user_id": user_id,
                    "role_name": user_role,
                    "organization_id": None,
                    "business_id": None,
                    "is_primary": True,
                    "is_active": True,
                }
                user_data["user_role"] = user_role
                return user_data

            # Get user role information
            user_role_info = get_user_role_info(user_id)
            if not user_role_info:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied - no role information found"
                )

            user_role = user_role_info.get("role_name", "").lower()

            # Allow access only for super-admin role
            if user_role != "super-admin":
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied - requires super-admin role, current role: {user_role}"
                )

            # Add role information to user_data for use in endpoints
            user_data["role_info"] = user_role_info
            user_data["user_role"] = user_role

            return user_data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in super-admin role checking: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Internal server error during super-admin role verification"
            )

    return dependency


def check_organization_access(user_data: dict, requested_org_id: str) -> bool:
    """
    Helper function to check if a user can access a specific organization
    
    Args:
        user_data: User data dict from authentication decorator
        requested_org_id: Organization ID being requested
        
    Returns:
        bool: True if user can access the organization, False otherwise
    """
    try:
        user_role = user_data.get("user_role", "").lower()
        
        # Super-admin can access any organization
        if user_role == "super-admin":
            return True
        
        # Admin / org-admin / coach-admin can only access their own organization
        if user_role in ("admin", "org-admin", "coach-admin"):
            user_role_info = user_data.get("role_info", {})
            user_org_id = user_role_info.get("organization_id")
            return user_org_id == requested_org_id

        # Other roles have no organization access
        return False
        
    except Exception as e:
        logger.error(f"Error checking organization access: {str(e)}")
        return False


def get_user_accessible_organizations(user_data: dict) -> list:
    """
    Helper function to get list of organization IDs that a user can access
    
    Args:
        user_data: User data dict from authentication decorator
        
    Returns:
        list: List of organization IDs the user can access
    """
    try:
        user_role = user_data.get("user_role", "").lower()
        
        # Super-admin can access all organizations (return empty list to indicate "all")
        if user_role == "super-admin":
            return []  # Empty list means "all organizations"
        
        # Admin / org-admin / coach-admin can only access their own organization
        if user_role in ("admin", "org-admin", "coach-admin"):
            user_role_info = user_data.get("role_info", {})
            user_org_id = user_role_info.get("organization_id")
            return [user_org_id] if user_org_id else []

        # Other roles have no organization access
        return []

    except Exception as e:
        logger.error(f"Error getting accessible organizations: {str(e)}")
        return []
