from fastapi import APIRouter, Depends, Query
from fastapi_utils.cbv import cbv
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
)
from prism_inspire.core.log_config import logger
from users.decorators import require_admin_role, require_super_admin_role
from users.dashboard.schema import (
    get_document_count_by_categories,
    get_each_organization_details,
    get_organization_stats,
    get_business_stats, get_license_stats
)


dashboard_routes = APIRouter(prefix="/dashboard", tags=["Dashboard & Analytics"])

went_wrong = "Something went wrong, please try again later"


@cbv(dashboard_routes)
class DashboardView:
    @dashboard_routes.get("/organization/stats", response_model=dict)
    def get_organization_statistics(
        self,
        user_data: dict = Depends(require_admin_role())
    ):
        """Get organization-specific statistics"""
        try:
            user_id = user_data["sub"]
            user_role = user_data["user_role"]
            is_super_admin = user_role == "super-admin"

            stats = get_each_organization_details(user_id, is_super_admin=is_super_admin)
            
            return create_response(
                message="Organization statistics retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=stats
            )
            
        except Exception as e:
            logger.error(f"Error getting organization statistics: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @dashboard_routes.get("/licenses/stats", response_model=dict)
    def get_license_statistics(
        self,
        expiring_days: int = Query(30, ge=1, le=365, description="Days to consider for expiring licenses"),
        user_data: dict = Depends(require_admin_role())
    ):
        """Get license-specific statistics"""
        try:
            stats = get_license_stats(expiring_days=expiring_days)
            
            return create_response(
                message="License statistics retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=stats
            )
            
        except Exception as e:
            logger.error(f"Error getting license statistics: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @dashboard_routes.get("/system", response_model=dict)
    def get_system_dashboard(
        self,
        user_data: dict = Depends(require_super_admin_role())
    ):
        """Get system-level dashboard - Super-admin only"""
        try:
            org_stats = get_organization_stats()
            business_stats = get_business_stats()

            org_breakdown = {
                "total": org_stats.get("total_organizations", 0),
                "active": org_stats.get("active_organizations", 0),
                "inactive": org_stats.get("total_organizations", 0) - org_stats.get("active_organizations", 0)
            }

            business_breakdown = {
                "total": business_stats.get("total_businesses", 0),
                "active": business_stats.get("active_businesses", 0),
                "inactive": business_stats.get("total_businesses", 0) - business_stats.get("active_businesses", 0),
                "by_type": {
                    "corporate": business_stats.get("businesses_by_type", {}).get("corporate", 0),
                    "education": business_stats.get("businesses_by_type", {}).get("education", 0),
                }
            }

            # Combine system data
            system_data = {
                "organization_statistics": org_breakdown,
                "business_statistics": business_breakdown
            }

            return create_response(
                message="System dashboard data retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=system_data
            )

        except Exception as e:
            logger.error(f"Error getting system dashboard: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @dashboard_routes.get("/documents/count", response_model=dict)
    def get_document_trends(
        self,
        user_data: dict = Depends(require_super_admin_role())
    ):
        """Get files uploaded count by each category"""
        try:
            documents_count = get_document_count_by_categories()
            
            return create_response(
                message="documents counts retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=documents_count
            )
            
        except Exception as e:
            logger.error(f"Error getting documents counts: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )
