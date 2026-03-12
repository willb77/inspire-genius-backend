from fastapi import APIRouter, Depends, Path, Query
from fastapi_utils.cbv import cbv
from typing import Optional
from uuid import UUID
from users.response import (
    VALIDATION_ERROR_CODE,
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from users.decorators import (
    require_super_admin_role, require_admin_role, 
    get_user_accessible_organizations, check_organization_access
)
from users.license.req_resp_parser import (
    CreateLicenseRequest, UpdateLicenseRequest
)
from users.license.schema import (
    create_license, get_license_by_id, update_license,
    get_licenses
)
from users.models.license import SubscriptionTierEnum, LicenseStatusEnum


license_routes = APIRouter(prefix="/licenses", tags=["License Management"])

went_wrong = "Something went wrong, please try again later"


@cbv(license_routes)
class LicenseManagementView:
    
    @license_routes.post("/", response_model=dict)
    def create_license(
        self,
        license_request: CreateLicenseRequest,
        user_data: dict = Depends(require_super_admin_role())
    ):
        """Create a new license for an organization - Super-admin only"""
        try:            
            license_data = {
                "organization_id": str(license_request.organization_id),
                "subscription_tier": license_request.subscription_tier,
                "start_date": license_request.start_date,
                "end_date": license_request.end_date,
            }
            
            # Create license
            result = create_license(license_data)
            
            if not result["status"]:
                return create_response(
                    message=result["message"],
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            return create_response(
                message=result["message"],
                error_code=SUCCESS_CODE,
                status=True,
                data={"license_id": result["license_id"]}
            )
                        
        except Exception as e:
            logger.error(f"Error creating license: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @license_routes.get("/", response_model=dict)
    def list_licenses(
        self,
        organization_id: Optional[UUID] = Query(None),
        status: Optional[LicenseStatusEnum] = Query(None),
        subscription_tier: Optional[SubscriptionTierEnum] = Query(None),
        expiring_within_days: Optional[int] = Query(None, ge=1, le=365),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=100),
        user_data: dict = Depends(require_admin_role())
    ):
        """List licenses with filtering options"""
        try:
            # Check access permissions using centralized approach
            accessible_org_ids = get_user_accessible_organizations(user_data)

            if accessible_org_ids:  # Admin user - organization scoped
                user_org_id = accessible_org_ids[0]

                # Admin can only see their organization's licenses
                if organization_id and str(organization_id) != user_org_id:
                    return create_response(
                        message="Access denied to this organization",
                        error_code=FORBIDDEN_ERROR_CODE,
                        status=False,
                        status_code=403
                    )

                # If no organization_id specified, default to user's organization
                if not organization_id and user_org_id:
                    organization_id = UUID(user_org_id)
            
            # Get licenses
            licenses = get_licenses(
                organization_id=str(organization_id) if organization_id else None,
                status=status.value if status else None,
                subscription_tier=subscription_tier.value if subscription_tier else None,
                expiring_within_days=expiring_within_days,
                page=page,
                limit=limit
            )
            
            # Convert to response format
            license_responses = []
            for license in licenses:
                license_responses.append({
                    "id": str(license.id),
                    "organization_id": str(license.organization_id),
                    "organization_name": license.organization.name,
                    "subscription_tier": license.subscription_tier,
                    "start_date": license.start_date.isoformat(),
                    "end_date": license.end_date.isoformat(),
                    "status": license.status,
                    "is_expiring_soon": license.is_expiring_soon,
                    "days_until_expiry": license.days_until_expiry,
                    "created_at": license.created_at.isoformat(),
                    "updated_at": license.updated_at.isoformat()
                })
            
            return create_response(
                message="Licenses retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "licenses": license_responses,
                    "total": len(license_responses),
                    "page": page,
                    "limit": limit
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing licenses: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @license_routes.get("/{license_id}", response_model=dict)
    def get_license(
        self,
        license_id: UUID = Path(...),
        user_data: dict = Depends(require_admin_role())
    ):
        """Get license details by ID"""
        try:            
            # Get license
            license_obj = get_license_by_id(str(license_id))
            
            if not license_obj:
                return create_response(
                    message="License not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )
            
            if not check_organization_access(user_data, str(license_obj.organization_id)):
                return create_response(
                    message="Access denied to this license",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )
            
            license_data = {
                "id": str(license_obj.id),
                "organization_id": str(license_obj.organization_id),
                "subscription_tier": license_obj.subscription_tier,
                "status": license_obj.status,
                "start_date": license_obj.start_date.isoformat(),
                "end_date": license_obj.end_date.isoformat(),
                "is_active": license_obj.is_active,
                "is_expiring_soon": license_obj.is_expiring_soon,
                "days_until_expiry": license_obj.days_until_expiry,
                "created_at": license_obj.created_at.isoformat(),
                "updated_at": license_obj.updated_at.isoformat()
            }
            
            return create_response(
                message="License retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=license_data
            )
            
        except Exception as e:
            logger.error(f"Error getting license: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @license_routes.put("/{license_id}", response_model=dict)
    def update_license(
        self,
        license_id: UUID = Path(...),
        update_request: UpdateLicenseRequest = ...,
        user_data: dict = Depends(require_super_admin_role())
    ):
        """Update license details - Super-admin only"""
        try:
            # Get existing license
            license_obj = get_license_by_id(str(license_id))
            
            if not license_obj:
                return create_response(
                    message="License not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )
            
            # Prepare update data
            update_data = {}
            if update_request.subscription_tier:
                update_data["subscription_tier"] = update_request.subscription_tier.value
            if update_request.status:
                update_data["status"] = update_request.status.value
            if update_request.start_date:
                update_data["start_date"] = update_request.start_date
            if update_request.end_date:
                update_data["end_date"] = update_request.end_date
            
            # Update license
            success = update_license(str(license_id), update_data)
            
            if success:
                return create_response(
                    message="License updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            
            return create_response(
                message="Failed to update license",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
            
        except Exception as e:
            logger.error(f"Error updating license: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )
