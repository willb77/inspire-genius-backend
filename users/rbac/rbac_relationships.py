from fastapi import APIRouter, Depends, Path
from fastapi_utils.cbv import cbv
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.rbac.req_resp_parser import (
    RolePermissionRequest, GroupPermissionRequest
)
from users.rbac.schema import (
    # Role-Permission operations
    assign_permission_to_role,
    remove_permission_from_role,
    get_role_permissions,
    # Group-Permission operations
    assign_permission_to_group,
    remove_permission_from_group,
    get_group_permissions
)
from uuid import UUID
from users.rbac.rbac_routes import went_wrong

rbac_relationship_route = APIRouter(
    prefix="/rbac", tags=["RBAC Relationships"]
)


# Role-Permission relationship endpoints
@cbv(rbac_relationship_route)
class RolePermissionView:
    @rbac_relationship_route.post("/roles/{role_id}/permissions")
    def assign_permission_to_role(
        self, role_permission_request: RolePermissionRequest,
        role_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            permission_id = role_permission_request.permission_id
            created_by = user_data.get("sub")

            assignment_id = assign_permission_to_role(
                role_id, permission_id, created_by
            )

            if assignment_id:
                return create_response(
                    message="Permission assigned to role successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"assignment_id": str(assignment_id)}
                )
            return create_response(
                message="Failed to assign permission to role",
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

    @rbac_relationship_route.get("/roles/{role_id}/permissions")
    def get_role_permissions(
        self, role_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            permissions = get_role_permissions(role_id)
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
                message="Role permissions retrieved successfully",
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

    @rbac_relationship_route.delete(
        "/roles/{role_id}/permissions/{permission_id}"
    )
    def remove_permission_from_role(
        self, role_id: UUID = Path(...),
        permission_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            success = remove_permission_from_role(role_id, permission_id)

            if success:
                return create_response(
                    message="Permission removed from role successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message=(
                    "Failed to remove permission from role "
                    "or assignment not found"
                ),
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


# Group-Permission relationship endpoints
@cbv(rbac_relationship_route)
class GroupPermissionView:
    @rbac_relationship_route.post("/groups/{group_id}/permissions")
    def assign_permission_to_group(
        self, group_permission_request: GroupPermissionRequest,
        group_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            permission_id = group_permission_request.permission_id
            created_by = user_data.get("sub")

            assignment_id = assign_permission_to_group(
                group_id, permission_id, created_by
            )

            if assignment_id:
                return create_response(
                    message="Permission assigned to group successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"assignment_id": str(assignment_id)}
                )
            return create_response(
                message="Failed to assign permission to group",
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

    @rbac_relationship_route.get("/groups/{group_id}/permissions")
    def get_group_permissions(
        self, group_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            permissions = get_group_permissions(group_id)
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
                message="Group permissions retrieved successfully",
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

    @rbac_relationship_route.delete(
        "/groups/{group_id}/permissions/{permission_id}"
    )
    def remove_permission_from_group(
        self, group_id: UUID = Path(...),
        permission_id: UUID = Path(...),
        user_data: dict = Depends(verify_token)
    ):
        try:
            success = remove_permission_from_group(group_id, permission_id)

            if success:
                return create_response(
                    message="Permission removed from group successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message=("Failed to remove permission from group "
                         "or assignment not found"),
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
