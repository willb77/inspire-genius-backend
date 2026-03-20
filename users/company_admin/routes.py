"""
Company Admin API endpoints (2.2)

All endpoints require the 'company-admin' role (or super-admin).
Prefix: /v1/company-admin
"""
import uuid
from fastapi import APIRouter, Depends, Path, Query, Body
from typing import Optional

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role
from users.response import (
    create_response, SUCCESS_CODE, SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE, NOT_FOUND, FORBIDDEN_ERROR_CODE,
)
from users.models.user import Users, UserProfile, Organization, Business
from users.models.rbac import Roles
from users.models.license import License
from sqlalchemy.orm import joinedload
from sqlalchemy import func

company_admin_routes = APIRouter(prefix="/company-admin", tags=["Company Admin"])


def _get_org_id(user_data: dict) -> Optional[str]:
    """Extract the caller's organization_id from token context."""
    role_info = user_data.get("role_info", {})
    return role_info.get("organization_id")


# ---------------------------------------------------------------------------
#  GET /company-admin/users
# ---------------------------------------------------------------------------

@company_admin_routes.get("/users")
def list_org_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """All users in the admin's organization with filtering."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        if not org_id and user_data.get("user_role") != "super-admin":
            return create_response("Organization context required", False, FORBIDDEN_ERROR_CODE, status_code=403)

        query = (
            session.query(Users)
            .join(UserProfile, Users.user_id == UserProfile.user_id)
            .options(joinedload(Users.profile))
        )

        if org_id:
            query = query.filter(UserProfile.org_id == org_id)

        if search:
            term = f"%{search.lower()}%"
            query = query.filter(
                func.lower(Users.email).like(term)
                | func.lower(UserProfile.first_name).like(term)
                | func.lower(UserProfile.last_name).like(term)
            )

        if role:
            role_obj = session.query(Roles).filter(func.lower(Roles.name) == role.lower()).first()
            if role_obj:
                query = query.filter(UserProfile.role == role_obj.id)

        total = query.count()
        offset = (page - 1) * limit
        users = query.order_by(Users.created_at.desc()).offset(offset).limit(limit).all()

        users_data = []
        for u in users:
            p = u.profile
            r = session.query(Roles).filter(Roles.id == p.role).first() if p and p.role else None
            users_data.append({
                "user_id": str(u.user_id),
                "email": u.email,
                "first_name": p.first_name if p else None,
                "last_name": p.last_name if p else None,
                "role": r.name if r else None,
                "is_active": u.is_active,
                "is_email_verified": u.is_email_verified,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            })

        return create_response("Users retrieved", True, SUCCESS_CODE, data={
            "users": users_data,
            "pagination": {"total": total, "page": page, "limit": limit, "has_more": offset + limit < total},
        })
    except Exception as e:
        logger.error(f"Error listing org users: {e}")
        return create_response("Failed to list users", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /company-admin/users
# ---------------------------------------------------------------------------

@company_admin_routes.post("/users")
def provision_user(
    email: str = Body(...),
    first_name: str = Body(...),
    last_name: str = Body(""),
    role_name: str = Body("user"),
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Provision a new user in the organization (delegates to user-management invite flow)."""
    org_id = _get_org_id(user_data)
    return create_response("User provisioning prepared", True, SUCCESS_CODE, data={
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "role": role_name,
        "organization_id": org_id,
        "next_step": "use_user_management_invite_endpoint",
    })


# ---------------------------------------------------------------------------
#  PUT /company-admin/users/:id
# ---------------------------------------------------------------------------

@company_admin_routes.put("/users/{user_id}")
def update_user(
    user_id: str = Path(...),
    first_name: Optional[str] = Body(None),
    last_name: Optional[str] = Body(None),
    is_active: Optional[bool] = Body(None),
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Update a user in the organization."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        user = session.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return create_response("User not found", False, NOT_FOUND, status_code=404)

        profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if org_id and profile and str(profile.org_id) != org_id:
            return create_response("User not in your organization", False, FORBIDDEN_ERROR_CODE, status_code=403)

        updated = []
        if first_name is not None and profile:
            profile.first_name = first_name
            updated.append("first_name")
        if last_name is not None and profile:
            profile.last_name = last_name
            updated.append("last_name")
        if is_active is not None:
            user.is_active = is_active
            if profile:
                profile.is_active = is_active
            updated.append("is_active")

        if not updated:
            return create_response("No fields to update", False, VALIDATION_ERROR_CODE, status_code=400)

        session.commit()
        return create_response("User updated", True, SUCCESS_CODE, data={"user_id": user_id, "updated": updated})
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating user: {e}")
        return create_response("Failed to update user", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  DELETE /company-admin/users/:id
# ---------------------------------------------------------------------------

@company_admin_routes.delete("/users/{user_id}")
def remove_user(
    user_id: str = Path(...),
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Soft-delete a user from the organization."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        user = session.query(Users).filter(Users.user_id == user_id).first()
        if not user:
            return create_response("User not found", False, NOT_FOUND, status_code=404)

        profile = session.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if org_id and profile and str(profile.org_id) != org_id:
            return create_response("User not in your organization", False, FORBIDDEN_ERROR_CODE, status_code=403)

        user.is_active = False
        user.is_deleted = True
        if profile:
            profile.is_active = False
        session.commit()

        return create_response("User removed", True, SUCCESS_CODE, data={"user_id": user_id})
    except Exception as e:
        session.rollback()
        logger.error(f"Error removing user: {e}")
        return create_response("Failed to remove user", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /company-admin/settings
# ---------------------------------------------------------------------------

@company_admin_routes.get("/settings")
def get_settings(
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Get organization-wide settings."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        if not org_id:
            return create_response("Organization context required", False, FORBIDDEN_ERROR_CODE, status_code=403)

        org = session.query(Organization).filter(Organization.id == org_id, Organization.is_deleted.is_(False)).first()
        if not org:
            return create_response("Organization not found", False, NOT_FOUND, status_code=404)

        return create_response("Settings retrieved", True, SUCCESS_CODE, data={
            "organization_id": str(org.id),
            "name": org.name,
            "contact": org.contact,
            "email": org.email,
            "address": org.address,
            "website_url": org.website_url,
            "type": org.type.value if org.type else None,
            "is_onboarded": org.is_onboarded,
        })
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return create_response("Failed to get settings", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  PUT /company-admin/settings
# ---------------------------------------------------------------------------

@company_admin_routes.put("/settings")
def update_settings(
    name: Optional[str] = Body(None),
    contact: Optional[str] = Body(None),
    email: Optional[str] = Body(None),
    address: Optional[str] = Body(None),
    website_url: Optional[str] = Body(None),
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Update organization-wide settings."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        if not org_id:
            return create_response("Organization context required", False, FORBIDDEN_ERROR_CODE, status_code=403)

        org = session.query(Organization).filter(Organization.id == org_id, Organization.is_deleted.is_(False)).first()
        if not org:
            return create_response("Organization not found", False, NOT_FOUND, status_code=404)

        updated = []
        if name is not None:
            org.name = name
            updated.append("name")
        if contact is not None:
            org.contact = contact
            updated.append("contact")
        if email is not None:
            org.email = email
            updated.append("email")
        if address is not None:
            org.address = address
            updated.append("address")
        if website_url is not None:
            org.website_url = website_url
            updated.append("website_url")

        if not updated:
            return create_response("No fields to update", False, VALIDATION_ERROR_CODE, status_code=400)

        session.commit()
        return create_response("Settings updated", True, SUCCESS_CODE, data={"updated": updated})
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating settings: {e}")
        return create_response("Failed to update settings", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /company-admin/analytics
# ---------------------------------------------------------------------------

@company_admin_routes.get("/analytics")
def get_analytics(
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Organization dashboard — departments, teams, training progress, PRISM coverage."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        if not org_id:
            return create_response("Organization context required", False, FORBIDDEN_ERROR_CODE, status_code=403)

        total_users = session.query(func.count(UserProfile.id)).filter(
            UserProfile.org_id == org_id, UserProfile.is_active.is_(True)
        ).scalar() or 0

        total_businesses = session.query(func.count(Business.id)).filter(
            Business.organization_id == org_id, Business.is_deleted.is_(False)
        ).scalar() or 0

        # Department breakdown via EmployeeProfile
        from users.models.user import EmployeeProfile
        dept_counts = (
            session.query(EmployeeProfile.department, func.count(EmployeeProfile.id))
            .join(UserProfile, EmployeeProfile.user_profile_id == UserProfile.id)
            .filter(UserProfile.org_id == org_id)
            .group_by(EmployeeProfile.department)
            .all()
        )
        departments = [{"name": d or "Unassigned", "count": c} for d, c in dept_counts]

        # Training progress
        from users.models.manager import TrainingAssignment, TrainingStatusEnum
        training_stats = (
            session.query(TrainingAssignment.status, func.count(TrainingAssignment.id))
            .join(Users, TrainingAssignment.user_id == Users.user_id)
            .join(UserProfile, Users.user_id == UserProfile.user_id)
            .filter(UserProfile.org_id == org_id, TrainingAssignment.is_deleted.is_(False))
            .group_by(TrainingAssignment.status)
            .all()
        )
        training = {s.value: c for s, c in training_stats}

        return create_response("Analytics retrieved", True, SUCCESS_CODE, data={
            "organization_id": org_id,
            "total_users": total_users,
            "total_departments": len(departments),
            "total_businesses": total_businesses,
            "departments": departments,
            "training_progress": training,
            "prism_coverage": None,  # placeholder until PRISM integration
        })
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return create_response("Failed to get analytics", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /company-admin/costs
# ---------------------------------------------------------------------------

@company_admin_routes.get("/costs")
def get_costs(
    user_data: dict = Depends(require_role("company-admin", "super-admin")),
):
    """Cost and expense reporting for the organization."""
    session = ScopedSession()
    try:
        org_id = _get_org_id(user_data)
        if not org_id:
            return create_response("Organization context required", False, FORBIDDEN_ERROR_CODE, status_code=403)

        licenses = (
            session.query(License)
            .filter(License.organization_id == org_id, License.is_deleted.is_(False))
            .all()
        )

        license_data = []
        for lic in licenses:
            license_data.append({
                "license_id": str(lic.id),
                "tier": lic.subscription_tier,
                "status": lic.status,
                "start_date": lic.start_date.isoformat() if lic.start_date else None,
                "end_date": lic.end_date.isoformat() if lic.end_date else None,
            })

        total_users = session.query(func.count(UserProfile.id)).filter(
            UserProfile.org_id == org_id, UserProfile.is_active.is_(True)
        ).scalar() or 0

        return create_response("Costs retrieved", True, SUCCESS_CODE, data={
            "organization_id": org_id,
            "licenses": license_data,
            "active_user_count": total_users,
            "estimated_monthly_cost": None,  # placeholder until billing integration
        })
    except Exception as e:
        logger.error(f"Error getting costs: {e}")
        return create_response("Failed to get costs", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()
