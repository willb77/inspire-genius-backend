from fastapi import APIRouter, Depends, Path, Query, File, UploadFile, Form
from fastapi_utils.cbv import cbv
from typing import Optional
from uuid import UUID

from users.auth import verify_token
# Simplified RBAC - using custom role decorator instead of complex permission system
from users.decorators import require_admin_role, require_super_admin_role, check_organization_access, get_user_accessible_organizations
from users.organization.req_resp_parser import (
    AgentOrganizationAssignRequest, AgentOrganizationRemoveRequest, BusinessCreateRequest,
    OrganizationUpdateRequest, BusinessUpdateRequest, AgentBusinessAssignRequest,
    AgentBusinessRemoveRequest
)
from users.models.user import OrganizationTypeEnum
from users.organization.schema import (
    create_business, create_organization, deactivate_business, get_all_organizations, get_organization_businesses, get_organization_by_id,
    deactivate_organization, assign_agents_to_organization, get_organization_agents, remove_agent_from_organization, update_business,
    generate_logo_url, get_organization_admin, update_organization, get_organization_details_for_response,
    assign_agents_to_business, get_business_agents_with_org_settings, remove_agent_from_business, get_business_with_admin_info
)
from users.license.schema import get_licenses
from users.models.license import License
from datetime import datetime, timezone
from ai.agent_settings.schema import get_org_agent_voice_details, get_agent_by_id
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from prism_inspire.core.file_utils import S3FileHandler

organization_routes = APIRouter(prefix="/organizations", tags=["Organization Management"])

went_wrong = "Something went wrong, please try again later"
ORGANIZATION_ID = "Organization ID"
ORGANIZATION_NOT_FOUND = "Organization not found"
ACCESS_DENIED = "Access denied - you can only manage your organization"

@cbv(organization_routes)
class OrganizationManagementView:
    @organization_routes.post("/", response_model=dict, summary="Create an organization",
                              description="Create a new organization with name, contact, type, and optional logo.")
    def create_organization(
        self,
        name: str = Form(..., description="Organization name", min_length=2, max_length=150),
        contact: str = Form(..., description="Contact phone number", min_length=10, max_length=15),
        type: OrganizationTypeEnum = Form(..., description="Organization type (both/education/corporate)"),
        email: Optional[str] = Form(None, description="Organization email address"),
        address: Optional[str] = Form(None, description="Organization address", max_length=500),
        website_url: Optional[str] = Form(None, description="Organization website URL", max_length=255),
        logo: Optional[UploadFile] = File(None, description="Organization logo image file (PNG, JPG, JPEG)"),
        user_data: dict = Depends(require_super_admin_role())
    ):
        """Create a new organization with type and auto-create business(es) - Super-admin only"""
        try:
            user_id = user_data["sub"]

            # Prepare organization data
            data = {
                "name": name,
                "contact": contact,
                "type": type,
                "email": email,
                "address": address,
                "website_url": website_url,
                "created_by": user_id
            }

            # Handle logo upload if provided
            logo_s3_key = None
            if logo:
                # Validate logo file type
                allowed_types = ["image/png", "image/jpeg", "image/jpg"]
                if logo.content_type not in allowed_types:
                    return create_response(
                        message=f"Invalid logo file type. Allowed types: PNG, JPG, JPEG",
                        error_code=VALIDATION_ERROR_CODE,
                        status=False,
                        status_code=400
                    )

                # Upload logo to S3
                file_handler = S3FileHandler(prefix="organization-logos/")
                logo_s3_key = file_handler.save_file(logo, user_id=user_id)

                if not logo_s3_key:
                    return create_response(
                        message="Failed to upload logo to S3",
                        error_code=SOMETHING_WENT_WRONG,
                        status=False,
                        status_code=500
                    )

                data["logo"] = logo_s3_key

            organization_id = create_organization(data)

            if organization_id:
                return create_response(
                    message="Organization created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={
                        "organization_id": organization_id,
                        "logo_uploaded": logo_s3_key is not None
                    }
                )
            return create_response(
                message="Failed to create organization",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        except Exception as e:
            logger.error(f"Error creating organization: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )
        
    @organization_routes.put("/{org_id}", response_model=dict)
    def update_organization(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        request: OrganizationUpdateRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """Update organization details (type field not allowed to be updated)"""
        try:
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message=ACCESS_DENIED,
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Verify organization exists
            organization = get_organization_by_id(org_id)
            if not organization:
                return create_response(
                    message=ORGANIZATION_NOT_FOUND,
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            # Update organization
            data = request.model_dump(exclude_none=True)
            success = update_organization(org_id, data)

            if success:
                return create_response(
                    message="Organization updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )

            return create_response(
                message="Failed to update organization",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        except Exception as e:
            logger.error(f"Error updating organization: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.delete("/{org_id}", response_model=dict)
    def delete_organization(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        user_data: dict = Depends(require_super_admin_role())
    ):
        """delete a new organization - Super-admin only"""
        try:
            status = deactivate_organization(org_id)

            if status:
                return create_response(
                    message="Organization deactivated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            return create_response(
                message="Failed to deactivate organization",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        except Exception as e:
            logger.error(f"Error deactivating organization: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.get("/", response_model=dict)
    def list_organizations(
        self,
        type: Optional[str] = Query(None, description = "Filter by organization type"),
        name: Optional[str] = Query(None, description = "Filter by organization name"),
        sort: Optional[str] = Query(None, description = "Sort order: 'asc' or 'desc' by created date"),
        page: int = Query(1, ge=1),
        limit: int = Query(10, ge=1, le=100),
        user_data: dict = Depends(require_admin_role())
    ):
        """List organizations with role-based filtering"""
        try:
            # Check if user is admin (organization-scoped) or super-admin (system-wide)
            accessible_org_ids = get_user_accessible_organizations(user_data)
            
            if accessible_org_ids:  # Admin user - organization scoped
                # Admin users can only see their organization
                org_list = []
                for org_id in accessible_org_ids:
                    org_data = get_organization_details_for_response(org_id, include_full_details=False)
                    if org_data:
                        if (not type or org_data.get("type") == type) and\
                           (not name or name.lower() in org_data.get("name", "").lower()):
                            org_list.append(org_data)

                if sort:
                    reverse = sort.lower() == 'desc'
                    org_list.sort(
                        key=lambda x: datetime.fromisoformat(x.get("created_at")) if x.get("created_at")else datetime.min,
                        reverse=reverse)
                total = len(org_list)

                return create_response(
                    message="Organizations retrieved successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={
                        "organizations": org_list,
                        "total": total,
                        "page": page,
                        "limit": limit
                    }
                )
            else:  # Super-admin user - system-wide access
                result = get_all_organizations(page=page, limit=limit)

                if result:
                    # Build organization list with basic details only
                    org_list = []
                    for org in result["organizations"]:
                        org_data = get_organization_details_for_response(str(org.id), include_full_details=False)
                        if org_data:
                            if (not type or org_data.get("type") == type) and\
                               (not name or name.lower() in org_data.get("name", "").lower()):
                                org_list.append(org_data)
                    
                    if sort:
                        reverse = sort.lower() == 'desc'
                        org_list.sort(
                            key=lambda x: datetime.fromisoformat(x.get("created_at")) if x.get("created_at")else datetime.min,
                            reverse=reverse)

                    return create_response(
                        message="Organizations retrieved successfully",
                        error_code=SUCCESS_CODE,
                        status=True,
                        data={
                            "organizations": org_list,
                            "total": result["total"],
                            "page": result["page"],
                            "limit": result["limit"]
                        }
                    )
                return create_response(
                    message="No organizations found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )
                
        except Exception as e:
            logger.error(f"Error listing organizations: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.get("/{org_id}", response_model=dict)
    def get_organization(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        user_data: dict = Depends(require_admin_role())
    ):
        """Get organization details with proper access control"""
        try:
            # Check organization access using centralized function
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message="Access denied - you can only view your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            org_data = get_organization_details_for_response(org_id, include_full_details=True)

            if org_data:
                return create_response(
                    message="Organization retrieved successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data=org_data
                )

            return create_response(
                message=ORGANIZATION_NOT_FOUND,
                error_code=NOT_FOUND,
                status=False,
                status_code=404
            )
        except Exception as e:
            logger.error(f"Error getting organization: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.get("/{org_id}/agents", response_model=dict)
    def get_organization_agents(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: Optional[str] = Query(None, description="Business ID to check agent assignments"),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Get all agents assigned to a specific organization

        If business_id is provided, returns all organization agents with an additional flag
        'is_assigned_to_business' indicating whether each agent is assigned to that business.

        This endpoint requires admin or super-admin role access.
        Regular users are denied access.
        """
        try:
            # Check if organization exists
            organization = get_organization_by_id(org_id)
            if not organization:
                return create_response(
                    message=ORGANIZATION_NOT_FOUND,
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            # Check organization access using centralized function
            if not check_organization_access(user_data, str(org_id)):
                return create_response(
                    message="Access denied - you can only view agents for your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Get agents assigned to the organization
            agents = get_organization_agents(org_id)

            # If business_id is provided, get business agents to check assignments
            business_agent_ids = set()
            if business_id:
                business_agents = get_business_agents_with_org_settings(business_id)
                business_agent_ids = {str(ba["agent_id"]) for ba in business_agents}

            serialized_agents = []
            for agent in agents:
                _agent = get_agent_by_id(str(agent.agent_id))
                agent_name = _agent.name if _agent else  None
                agent_data = {
                    "id": str(agent.id),
                    "agent_name": agent_name,
                    "agent_id": str(agent.agent_id),
                    "organization_id": str(agent.organization_id),
                    "assigned_by": str(agent.assigned_by) if agent.assigned_by else None,
                    "is_active": agent.is_active,
                    "preferences": {
                        "accent": {
                            "id": str(agent.accent.id),
                            "name": agent.accent.name
                        } if agent.accent else None,
                        "gender": {
                            "id": str(agent.gender.id),
                            "name": agent.gender.name
                        } if agent.gender else None,
                        "tones": [
                            {
                                "id": str(tone_assoc.tone.id),
                                "name": tone_assoc.tone.name
                            }
                            for tone_assoc in agent.tones
                        ] if agent.tones else []
                    },
                    "created_at": agent.created_at.isoformat() if agent.created_at else None,
                    "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
                }

                # Add is_assigned_to_business flag if business_id was provided
                if business_id:
                    agent_data["is_assigned_to_business"] = str(agent.agent_id) in business_agent_ids

                serialized_agents.append(agent_data)

            response_data = {
                "organization_id": org_id,
                "organization_name": organization.name,
                "agents": serialized_agents,
                "total_agents": len(agents) if agents else 0
            }

            # Include business_id in response if it was provided
            if business_id:
                response_data["business_id"] = business_id

            return create_response(
                message="Organization agents retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=response_data
            )

        except Exception as e:
            logger.error(f"Error getting organization agents: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @organization_routes.post("/{org_id}/agents/assign", response_model=dict)
    def assign_agent_to_organization(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        request: AgentOrganizationAssignRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Assign an agent to an organization

        This endpoint allows admins to assign agents to their organization.
        Super-admins can assign agents to any organization.
        """
        try:
            user_id = user_data["sub"]

            # Check if organization exists
            organization = get_organization_by_id(org_id)
            if not organization:
                return create_response(
                    message=ORGANIZATION_NOT_FOUND,
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            # Check organization access using centralized function
            if not check_organization_access(user_data, str(org_id)):
                return create_response(
                    message="Access denied - you can only assign agents to your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Convert preferences to dict format for schema function
            agent_preferences = [
                {
                    "agent_id": str(pref.agent_id),
                    "tone_ids": [str(t) for t in pref.tone_ids],
                    "accent_id": str(pref.accent_id) if pref.accent_id else None,
                    "gender_id": str(pref.gender_id) if pref.gender_id else None
                }
                for pref in request.preferences
            ]

            # Assign agents to organization with preferences
            result = assign_agents_to_organization(
                organization_id=org_id,
                agent_preferences=agent_preferences,
                assigned_by=user_id
            )

            if not result["success"]:
                return create_response(
                    message="No agents were assigned (failed)",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    data={
                        "organization_id": org_id,
                        "failed_agents": result["failed"]
                    },
                    status_code=400
                )

            return create_response(
                message="Agents assigned to organization successfully with preferences",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "organization_id": org_id,
                    "assigned_agents": result["success"],
                    "failed_agents": result["failed"],
                    "assigned_by": user_id
                }
            )

        except Exception as e:
            logger.error(f"Error assigning agent to organization: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @organization_routes.delete("/{org_id}/agents/delete", response_model=dict)
    def delete_agent_from_organization(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        request: AgentOrganizationRemoveRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Delete an agent from an organization

        This endpoint allows admins to delete agents from their organization.
        Super-admins can delete agents from any organization.
        """
        try:
            user_id = user_data["sub"]

            # Check if organization exists
            organization = get_organization_by_id(org_id)
            if not organization:
                return create_response(
                    message=ORGANIZATION_NOT_FOUND,
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            # Check organization access using centralized function
            if not check_organization_access(user_data, str(org_id)):
                return create_response(
                    message="Access denied - you can only delete agents from your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Delete agent from organization
            deleted_agents = []
            failed_agents = []

            for agent_id in request.agent_ids:
                success = remove_agent_from_organization(
                    organization_id=org_id,
                    agent_id=str(agent_id)
                )
                if success:
                    deleted_agents.append(agent_id)
                else:
                    failed_agents.append(agent_id)

            return create_response(
                message="Agent removed from organization successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "organization_id": org_id,
                    "deleted_agents": deleted_agents,
                    "failed_agents": failed_agents,
                    "deleted_by": user_id
                }
            )

        except Exception as e:
            logger.error(f"Error deleting agent from organization: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )
        
    
    @organization_routes.post("/{org_id}/businesses", response_model=dict)
    def create_business(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_request: BusinessCreateRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """Create a new business within an organization"""
        try:            
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message=ACCESS_DENIED,
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )
            
            # Verify organization exists
            organization = get_organization_by_id(org_id)
            if not organization:
                return create_response(
                    message=ORGANIZATION_NOT_FOUND,
                    error_code=NOT_FOUND,
                    status=False, 
                    status_code=404
                )
            
            data = business_request.model_dump()
            data["organization_id"] = org_id
            
            business_id = create_business(data)
            
            if business_id:
                return create_response(
                    message="Business created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"business_id": business_id}
                )
            
            return create_response(
                message="Failed to create business - maximum limit reached or validation error",
                error_code=VALIDATION_ERROR_CODE,
                status=False,
                status_code=400
            )
            
        except Exception as e:
            logger.error(f"Error creating business: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.put("/{org_id}/businesses/{business_id}", response_model=dict)
    def update_business(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: str = Path(..., description="Business ID"),
        business_request: BusinessUpdateRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """Update business name only and set is_onboarded=True"""
        try:
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message=ACCESS_DENIED,
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            data = business_request.model_dump()
            success = update_business(business_id, data)

            if success:
                return create_response(
                    message="Business updated successfully and marked as onboarded",
                    error_code=SUCCESS_CODE,
                    status=True
                )

            return create_response(
                message="Business not found or update failed",
                error_code=NOT_FOUND,
                status=False,
                status_code=404
            )

        except Exception as e:
            logger.error(f"Error updating business: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.delete("/{org_id}/businesses/{business_id}", response_model=dict)
    def delete_business(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: str = Path(..., description="Business ID"),
        user_data: dict = Depends(require_admin_role())
    ):
        """Delete/deactivate a business"""
        try:            
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message=ACCESS_DENIED,
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )
            
            success = deactivate_business(business_id)
            
            if success:
                return create_response(
                    message="Business deactivated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )
            
            return create_response(
                message="Business not found or deactivation failed",
                error_code=NOT_FOUND,
                status=False,
                status_code=404
            )
            
        except Exception as e:
            logger.error(f"Error deactivating business: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @organization_routes.get("/{org_id}/businesses", response_model=dict)
    def list_businesses(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        user_data: dict = Depends(require_admin_role())
    ):
        """List all businesses for an organization"""
        try:            
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message="Access denied - you can only view your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )
            
            businesses = get_organization_businesses(org_id)

            return create_response(
                message="Businesses retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "businesses": [
                        get_business_with_admin_info(org_id, business)
                        for business in businesses
                    ],
                    "total": len(businesses)
                }
            )
            
        except Exception as e:
            logger.error(f"Error listing businesses: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    # ============ Business Agent Assignment Endpoints ============

    @organization_routes.get("/{org_id}/businesses/{business_id}/agents", response_model=dict)
    def get_business_assigned_agents(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: str = Path(..., description="Business ID"),
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Get all agents assigned to a business with organization settings

        This endpoint returns all agents assigned to a specific business.
        Business uses the same agent settings as the parent organization.
        """
        try:
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message="Access denied - you can only view agents for your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Get business agents with organization settings
            business_agents = get_business_agents_with_org_settings(business_id)

            # Format response with organization settings
            agents_data = []
            for ba_data in business_agents:
                org_agent = ba_data["org_agent"]
                agent_details = get_org_agent_voice_details(str(ba_data["agent_id"]))

                # Get tone details from organization agent
                tone_details = []
                for tone_assoc in org_agent.tones:
                    tone_details.append({
                        "id": str(tone_assoc.tone_id),
                        "name": tone_assoc.tone.name if hasattr(tone_assoc, 'tone') else None
                    })

                agents_data.append({
                    "business_assignment_id": str(ba_data["business_assignment_id"]),
                    "agent_id": str(ba_data["agent_id"]),
                    "agent_name": agent_details.get("name") if agent_details else None,
                    "is_active": ba_data["is_active"],
                    "created_at": ba_data["created_at"].isoformat() if ba_data["created_at"] else None,
                    "settings_from_organization": {
                        "accent": {
                            "accent_id": str(org_agent.accent_id) if org_agent.accent_id else None,
                            "name": org_agent.accent.name if org_agent.accent else None
                        },
                        "gender_id": {
                            "gender_id": str(org_agent.gender_id) if org_agent.gender_id else None,
                            "name": org_agent.gender.name if org_agent.gender else None
                        },
                        "tones": tone_details
                    }
                })

            return create_response(
                message="Business agents retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "business_id": business_id,
                    "agents": agents_data,
                    "total": len(agents_data)
                }
            )

        except Exception as e:
            logger.error(f"Error fetching business agents: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @organization_routes.post("/{org_id}/businesses/{business_id}/agents/assign", response_model=dict)
    def assign_agents_to_business_endpoint(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: str = Path(..., description="Business ID"),
        request: AgentBusinessAssignRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Give business access to agents from organization

        This endpoint allows admins to give a business access to specific agents.
        Only agents assigned to the parent organization can be given to a business.
        Business uses the same agent settings as the organization (no separate preferences).
        """
        try:
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message="Access denied - you can only assign agents to businesses in your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Assign agents to business (just agent IDs, no preferences)
            agent_ids = [str(agent_id) for agent_id in request.agent_ids]
            result = assign_agents_to_business(
                business_id=business_id,
                agent_ids=agent_ids
            )

            return create_response(
                message="Agents assigned to business successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "business_id": business_id,
                    "assigned_agents": result["success"],
                    "failed_agents": result["failed"],
                    "total_assigned": len(result["success"])
                }
            )

        except Exception as e:
            logger.error(f"Error assigning agents to business: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @organization_routes.delete("/{org_id}/businesses/{business_id}/agents/remove", response_model=dict)
    def remove_agent_from_business_endpoint(
        self,
        org_id: str = Path(..., description=ORGANIZATION_ID),
        business_id: str = Path(..., description="Business ID"),
        request: AgentBusinessRemoveRequest = None,
        user_data: dict = Depends(require_admin_role())
    ):
        """
        Remove agent access from a business

        This endpoint allows admins to remove agent access from a business.
        """
        try:
            # Check organization access
            if not check_organization_access(user_data, org_id):
                return create_response(
                    message="Access denied - you can only remove agents from businesses in your organization",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Remove agents from business
            removed_agents = []
            failed_agents = []

            for agent_id in request.agent_ids:
                success = remove_agent_from_business(
                    business_id=business_id,
                    agent_id=str(agent_id)
                )
                if success:
                    removed_agents.append(str(agent_id))
                else:
                    failed_agents.append(str(agent_id))

            return create_response(
                message="Agents removed from business successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "business_id": business_id,
                    "removed_agents": removed_agents,
                    "failed_agents": failed_agents
                }
            )

        except Exception as e:
            logger.error(f"Error removing agents from business: {str(e)}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

