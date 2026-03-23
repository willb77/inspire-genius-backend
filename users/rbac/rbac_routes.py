from fastapi import APIRouter, Depends, Path
from fastapi_utils.cbv import cbv
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from users.decorators import require_super_admin_role
from users.rbac.req_resp_parser import (
    RoleRequest, RoleUpdateRequest, GroupRequest, GroupUpdateRequest,
    PermissionRequest, PermissionUpdateRequest
)
from users.rbac.schema import (
    # Role operations
    create_role, get_all_roles, get_role_by_id, update_role, delete_role,
    # Group operations
    create_group, get_all_groups, get_group_by_id, update_group, delete_group,
    # Permission operations
    create_permission, get_all_permissions, get_permission_by_id,
    update_permission, delete_permission,
)
from uuid import UUID

rbac_route = APIRouter(prefix="/rbac", tags=["RBAC"])

went_wrong = "Something went wrong, please try again later"


@cbv(rbac_route)
class RoleView:
    @rbac_route.post("/roles")
    def create_role(
        self,
        role_request: RoleRequest,
        user_data: dict = Depends(require_super_admin_role())
    ):
        try:
            data = role_request.model_dump()
            role_id = create_role(data)

            if role_id:
                return create_response(
                    message="Role created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"role_id": str(role_id)}
                )
            return create_response(
                message="Failed to create role",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/roles")
    def get_roles(
        self,
        user_data: dict = Depends(require_super_admin_role())
    ):
        try:
            roles = get_all_roles()
            roles_data = [
                {
                    "id": str(role.id),
                    "name": role.name,
                    "created_at": (
                        role.created_at.isoformat()
                        if role.created_at else None
                    ),
                    "updated_at": (
                        role.updated_at.isoformat()
                        if role.updated_at else None
                    )
                }
                for role in roles
            ]
            return create_response(
                message="Roles retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"roles": roles_data}
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/roles/{role_id}")
    def get_role(
        self, role_id: UUID = Path(...)
    ):
        try:
            role = get_role_by_id(role_id)

            if not role:
                return create_response(
                    message="Role not found",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            role_data = {
                "id": str(role.id),
                "name": role.name,
                "created_at": (
                    role.created_at.isoformat()
                    if role.created_at else None
                ),
                "updated_at": (
                    role.updated_at.isoformat()
                    if role.updated_at else None
                )
            }
            return create_response(
                message="Role retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=role_data
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.put("/roles/{role_id}")
    def update_role(
        self, role_request: RoleUpdateRequest,
        role_id: UUID = Path(...)
    ):
        try:
            data = role_request.model_dump()
            success = update_role(role_id, data)

            if success:
                return create_response(
                    message="Role updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to update role or role not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.delete("/roles/{role_id}")
    def delete_role(
        self, role_id: UUID = Path(...)
    ):
        try:
            success = delete_role(role_id)

            if success:
                return create_response(
                    message="Role deleted successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to delete role or role not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )


# Group endpoints
@cbv(rbac_route)
class GroupView:
    @rbac_route.post("/groups")
    def create_group(
        self, group_request: GroupRequest
    ):
        try:
            data = group_request.model_dump()
            group_id = create_group(data)

            if group_id:
                return create_response(
                    message="Group created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"group_id": str(group_id)}
                )
            return create_response(
                message="Failed to create group",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/groups")
    def get_groups(
        self
    ):
        try:
            groups = get_all_groups()
            groups_data = [
                {
                    "id": str(group.id),
                    "name": group.name,
                    "created_at": (
                        group.created_at.isoformat()
                        if group.created_at else None
                    ),
                    "updated_at": (
                        group.updated_at.isoformat()
                        if group.updated_at else None
                    )
                }
                for group in groups
            ]
            return create_response(
                message="Groups retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"groups": groups_data}
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/groups/{group_id}")
    def get_group(
        self, group_id: UUID = Path(...)
    ):
        try:
            group = get_group_by_id(group_id)

            if not group:
                return create_response(
                    message="Group not found",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            group_data = {
                "id": str(group.id),
                "name": group.name,
                "created_at": (
                    group.created_at.isoformat()
                    if group.created_at else None
                ),
                "updated_at": (
                    group.updated_at.isoformat()
                    if group.updated_at else None
                )
            }
            return create_response(
                message="Group retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=group_data
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.put("/groups/{group_id}")
    def update_group(
        self, group_request: GroupUpdateRequest,
        group_id: UUID = Path(...)
    ):
        try:
            data = group_request.model_dump()
            success = update_group(group_id, data)

            if success:
                return create_response(
                    message="Group updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to update group or group not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.delete("/groups/{group_id}")
    def delete_group(
        self, group_id: UUID = Path(...)
    ):
        try:
            success = delete_group(group_id)

            if success:
                return create_response(
                    message="Group deleted successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to delete group or group not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )


# Permission endpoints
@cbv(rbac_route)
class PermissionView:
    @rbac_route.post("/permissions")
    def create_permission(
        self, permission_request: PermissionRequest,
        user_data: dict = Depends(require_super_admin_role())
    ):
        try:
            data = permission_request.model_dump()
            data["created_by"] = user_data.get("sub")
            permission_id = create_permission(data)

            if permission_id:
                return create_response(
                    message="Permission created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"permission_id": str(permission_id)}
                )
            return create_response(
                message="Failed to create permission",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/permissions")
    def get_permissions(
        self
    ):
        try:
            permissions = get_all_permissions()
            permissions_data = [
                {
                    "id": str(permission.id),
                    "name": permission.name,
                    "created_by": (
                        str(permission.created_by)
                        if permission.created_by else None
                    ),
                    "created_at": (
                        permission.created_at.isoformat()
                        if permission.created_at else None
                    ),
                    "updated_at": (
                        permission.updated_at.isoformat()
                        if permission.updated_at else None
                    )
                }
                for permission in permissions
            ]
            return create_response(
                message="Permissions retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"permissions": permissions_data}
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.get("/permissions/{permission_id}")
    def get_permission(
        self, permission_id: UUID = Path(...)
    ):
        try:
            permission = get_permission_by_id(permission_id)

            if not permission:
                return create_response(
                    message="Permission not found",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            permission_data = {
                "id": str(permission.id),
                "name": permission.name,
                "created_by": (
                    str(permission.created_by)
                    if permission.created_by else None
                ),
                "created_at": (
                    permission.created_at.isoformat()
                    if permission.created_at else None
                ),
                "updated_at": (
                    permission.updated_at.isoformat()
                    if permission.updated_at else None
                )
            }
            return create_response(
                message="Permission retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=permission_data
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.put("/permissions/{permission_id}")
    def update_permission(
        self, permission_request: PermissionUpdateRequest,
        permission_id: UUID = Path(...)
    ):
        try:
            data = permission_request.model_dump()
            success = update_permission(permission_id, data)

            if success:
                return create_response(
                    message="Permission updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to update permission or permission not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @rbac_route.delete("/permissions/{permission_id}")
    def delete_permission(
        self, permission_id: UUID = Path(...)
    ):
        try:
            success = delete_permission(permission_id)

            if success:
                return create_response(
                    message="Permission deleted successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to delete permission or permission not found",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
        except Exception as e:
            logger.error(e)
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )
