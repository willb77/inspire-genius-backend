from decimal import Decimal
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Path, Query, UploadFile, File, Body
from pydantic import BaseModel, Field
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role_or_above, log_access
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    VALIDATION_ERROR_CODE,
    FORBIDDEN_ERROR_CODE,
)

from users.models.user import Users, UserProfile, EmployeeProfile, Organization, Business
from users.models.rbac import Roles
from users.models.license import License
from users.models.phase3 import UserGoal, UserActivity, CostRecord, OrgNode
from users.models.manager import TrainingAssignment

company_admin_routes = APIRouter(prefix="/company-admin", tags=["Company Admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org_id(user_data: dict):
    """Extract organization_id from the authenticated user's role info."""
    return (user_data.get("role_info") or {}).get("organization_id")


def _serialize_uuid(val):
    """Safely convert a UUID to string."""
    if val is None:
        return None
    return str(val)


def _serialize_decimal(val):
    """Convert Decimal / numeric to float for JSON."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    return val


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class InviteUserRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=150)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    role_name: str = Field(..., min_length=1, max_length=50)


class ChangeRoleRequest(BaseModel):
    role_name: str = Field(..., min_length=1, max_length=50)


# ---------------------------------------------------------------------------
# 1. GET /company-admin/overview — Org summary
# ---------------------------------------------------------------------------


@company_admin_routes.get("/overview")
def org_overview(user_data: dict = Depends(require_role_or_above("company-admin"))):
    log_access(user_data, "company_admin.overview")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Total users in org
        total_users = (
            session.query(func.count(UserProfile.id))
            .filter(UserProfile.org_id == org_id)
            .scalar()
        ) or 0

        # Active users in org
        active_users = (
            session.query(func.count(UserProfile.id))
            .filter(
                UserProfile.org_id == org_id,
                UserProfile.is_active == True,
            )
            .scalar()
        ) or 0

        # License info
        license_row = (
            session.query(License)
            .filter(
                License.organization_id == org_id,
                License.is_deleted == False,
            )
            .order_by(License.created_at.desc())
            .first()
        )

        license_info = None
        subscription_status = "none"
        if license_row:
            license_info = {
                "id": _serialize_uuid(license_row.id),
                "subscription_tier": license_row.subscription_tier,
                "status": license_row.status,
                "start_date": license_row.start_date.isoformat() if license_row.start_date else None,
                "end_date": license_row.end_date.isoformat() if license_row.end_date else None,
                "days_until_expiry": license_row.days_until_expiry,
            }
            subscription_status = license_row.status

        return create_response(
            "Organization overview retrieved successfully", True, SUCCESS_CODE,
            data={
                "organization_id": _serialize_uuid(org_id),
                "total_users": total_users,
                "active_users": active_users,
                "license": license_info,
                "subscription_status": subscription_status,
            },
        )

    except Exception as e:
        logger.error(f"Error fetching org overview: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 2. GET /company-admin/departments — List departments
# ---------------------------------------------------------------------------


@company_admin_routes.get("/departments")
def list_departments(user_data: dict = Depends(require_role_or_above("company-admin"))):
    log_access(user_data, "company_admin.departments")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Get distinct departments with employee counts
        dept_rows = (
            session.query(
                EmployeeProfile.department,
                func.count(EmployeeProfile.id).label("employee_count"),
            )
            .join(UserProfile, UserProfile.id == EmployeeProfile.user_profile_id)
            .filter(
                UserProfile.org_id == org_id,
                EmployeeProfile.department.isnot(None),
            )
            .group_by(EmployeeProfile.department)
            .all()
        )

        departments = []
        for dept_name, employee_count in dept_rows:
            # Get user_ids in this department for goal/training queries
            dept_user_ids = [
                uid
                for (uid,) in (
                    session.query(UserProfile.user_id)
                    .join(EmployeeProfile, EmployeeProfile.user_profile_id == UserProfile.id)
                    .filter(
                        UserProfile.org_id == org_id,
                        EmployeeProfile.department == dept_name,
                    )
                    .all()
                )
            ]

            # Active goals count
            active_goals = 0
            if dept_user_ids:
                active_goals = (
                    session.query(func.count(UserGoal.id))
                    .filter(
                        UserGoal.user_id.in_(dept_user_ids),
                        UserGoal.is_deleted == False,
                        UserGoal.status == "active",
                    )
                    .scalar()
                ) or 0

            # Training stats
            training_total = 0
            training_completed = 0
            if dept_user_ids:
                training_total = (
                    session.query(func.count(TrainingAssignment.id))
                    .filter(
                        TrainingAssignment.user_id.in_(dept_user_ids),
                        TrainingAssignment.is_deleted == False,
                    )
                    .scalar()
                ) or 0
                training_completed = (
                    session.query(func.count(TrainingAssignment.id))
                    .filter(
                        TrainingAssignment.user_id.in_(dept_user_ids),
                        TrainingAssignment.is_deleted == False,
                        TrainingAssignment.status == "completed",
                    )
                    .scalar()
                ) or 0

            departments.append({
                "department": dept_name,
                "employee_count": employee_count,
                "active_goals": active_goals,
                "avg_ig_interaction_pct": 0,  # placeholder
                "training_stats": {
                    "total": training_total,
                    "completed": training_completed,
                    "completion_rate": round(
                        (training_completed / training_total * 100) if training_total else 0, 1
                    ),
                },
                "ig_assessed_count": 0,  # placeholder
            })

        return create_response(
            "Departments retrieved successfully", True, SUCCESS_CODE,
            data={"departments": departments}
        )

    except Exception as e:
        logger.error(f"Error listing departments: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 3. GET /company-admin/departments/{dept_id} — Department detail
# ---------------------------------------------------------------------------


@company_admin_routes.get("/departments/{dept_id}")
def get_department_detail(
    dept_id: str = Path(..., description="Department name (URL-encoded)"),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.department_detail")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        dept_name = unquote(dept_id)

        # Verify department exists in org
        dept_exists = (
            session.query(EmployeeProfile.id)
            .join(UserProfile, UserProfile.id == EmployeeProfile.user_profile_id)
            .filter(
                UserProfile.org_id == org_id,
                EmployeeProfile.department == dept_name,
            )
            .first()
        )
        if not dept_exists:
            return create_response(
                "Department not found", False, NOT_FOUND, status_code=404
            )

        # Get members in this department
        members_query = (
            session.query(
                Users.user_id,
                Users.email,
                UserProfile.first_name,
                UserProfile.last_name,
                UserProfile.is_active,
                Roles.name.label("role_name"),
                EmployeeProfile.position,
                EmployeeProfile.employee_id,
                EmployeeProfile.hire_date,
            )
            .join(UserProfile, UserProfile.user_id == Users.user_id)
            .join(EmployeeProfile, EmployeeProfile.user_profile_id == UserProfile.id)
            .outerjoin(Roles, Roles.id == UserProfile.role)
            .filter(
                UserProfile.org_id == org_id,
                EmployeeProfile.department == dept_name,
            )
            .all()
        )

        members = []
        for row in members_query:
            members.append({
                "user_id": _serialize_uuid(row.user_id),
                "email": row.email,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "is_active": row.is_active,
                "role_name": row.role_name,
                "position": row.position,
                "employee_id": row.employee_id,
                "hire_date": row.hire_date.isoformat() if row.hire_date else None,
            })

        return create_response(
            "Department detail retrieved successfully", True, SUCCESS_CODE,
            data={
                "department": dept_name,
                "employee_count": len(members),
                "members": members,
            },
        )

    except Exception as e:
        logger.error(f"Error fetching department detail: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 4. GET /company-admin/departments/{dept_id}/members — Paginated members
# ---------------------------------------------------------------------------


@company_admin_routes.get("/departments/{dept_id}/members")
def list_department_members(
    dept_id: str = Path(..., description="Department name (URL-encoded)"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.department_members")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        dept_name = unquote(dept_id)

        # Base query
        base_q = (
            session.query(
                Users.user_id,
                Users.email,
                UserProfile.first_name,
                UserProfile.last_name,
                UserProfile.is_active,
                Roles.name.label("role_name"),
                EmployeeProfile.position,
                EmployeeProfile.employee_id,
                EmployeeProfile.hire_date,
            )
            .join(UserProfile, UserProfile.user_id == Users.user_id)
            .join(EmployeeProfile, EmployeeProfile.user_profile_id == UserProfile.id)
            .outerjoin(Roles, Roles.id == UserProfile.role)
            .filter(
                UserProfile.org_id == org_id,
                EmployeeProfile.department == dept_name,
            )
        )

        # Total count
        total_count = base_q.count()

        # Paginate
        offset = (page - 1) * limit
        rows = base_q.offset(offset).limit(limit).all()

        members = []
        for row in rows:
            members.append({
                "user_id": _serialize_uuid(row.user_id),
                "email": row.email,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "is_active": row.is_active,
                "role_name": row.role_name,
                "position": row.position,
                "employee_id": row.employee_id,
                "hire_date": row.hire_date.isoformat() if row.hire_date else None,
            })

        total_pages = (total_count + limit - 1) // limit if total_count else 0

        return create_response(
            "Department members retrieved successfully", True, SUCCESS_CODE,
            data={
                "department": dept_name,
                "members": members,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_count": total_count,
                    "total_pages": total_pages,
                },
            },
        )

    except Exception as e:
        logger.error(f"Error listing department members: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 5. POST /company-admin/organization/import — Import org structure
# ---------------------------------------------------------------------------


@company_admin_routes.post("/organization/import")
def import_organization(
    file: UploadFile = File(...),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.organization_import")
    try:
        filename = file.filename or "unknown"
        content_type = file.content_type or ""

        # Validate file type
        allowed_extensions = (".csv", ".json", ".xlsx")
        if not any(filename.lower().endswith(ext) for ext in allowed_extensions):
            return create_response(
                f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
                False,
                VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Placeholder: accept the file and return confirmation
        # Full parsing (CSV/JSON/XLSX) will be implemented in a follow-up
        return create_response(
            "File received successfully. Parsing will be implemented.",
            True,
            SUCCESS_CODE,
            data={
                "filename": filename,
                "content_type": content_type,
                "message": "File accepted. Organization structure parsing is pending implementation.",
                "tree": [],  # placeholder for parsed org tree
            },
        )

    except Exception as e:
        logger.error(f"Error importing organization: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )


# ---------------------------------------------------------------------------
# 6. GET /company-admin/organization/tree — Org hierarchy
# ---------------------------------------------------------------------------


def _build_tree(nodes_by_parent, parent_id=None):
    """Recursively build a nested tree from OrgNode records grouped by parent_id."""
    children = nodes_by_parent.get(parent_id, [])
    result = []
    for node in sorted(children, key=lambda n: (n.sort_order or 0, n.name)):
        result.append({
            "id": _serialize_uuid(node.id),
            "name": node.name,
            "title": node.title,
            "node_type": node.node_type,
            "parent_id": _serialize_uuid(node.parent_id),
            "user_id": _serialize_uuid(node.user_id),
            "children": _build_tree(nodes_by_parent, node.id),
        })
    return result


@company_admin_routes.get("/organization/tree")
def org_tree(user_data: dict = Depends(require_role_or_above("company-admin"))):
    log_access(user_data, "company_admin.organization_tree")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        nodes = (
            session.query(OrgNode)
            .filter(
                OrgNode.organization_id == org_id,
                OrgNode.is_deleted == False,
            )
            .all()
        )

        # Group nodes by parent_id
        nodes_by_parent: dict = {}
        for node in nodes:
            nodes_by_parent.setdefault(node.parent_id, []).append(node)

        tree = _build_tree(nodes_by_parent, parent_id=None)

        return create_response(
            "Organization tree retrieved successfully", True, SUCCESS_CODE,
            data={"tree": tree}
        )

    except Exception as e:
        logger.error(f"Error fetching org tree: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 7. POST /company-admin/users/invite — Invite user
# ---------------------------------------------------------------------------


@company_admin_routes.post("/users/invite")
def invite_user(
    body: InviteUserRequest,
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.users_invite")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Validate role exists
        role = (
            session.query(Roles)
            .filter(
                func.lower(Roles.name) == body.role_name.lower(),
                Roles.is_deleted == False,
            )
            .first()
        )
        if not role:
            return create_response(
                f"Role '{body.role_name}' not found",
                False,
                VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Check if user already exists in org
        existing = (
            session.query(Users.user_id)
            .join(UserProfile, UserProfile.user_id == Users.user_id)
            .filter(
                Users.email == body.email.lower(),
                UserProfile.org_id == org_id,
            )
            .first()
        )
        if existing:
            return create_response(
                "User with this email already exists in the organization",
                False,
                VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Delegate to existing invite flow (placeholder response)
        return create_response(
            "Invitation initiated successfully", True, SUCCESS_CODE,
            data={
                "email": body.email,
                "first_name": body.first_name,
                "last_name": body.last_name,
                "role_name": body.role_name,
                "organization_id": _serialize_uuid(org_id),
                "next_step": "invitation_email_sent",
            },
        )

    except Exception as e:
        logger.error(f"Error inviting user: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 8. PATCH /company-admin/users/{user_id}/role — Change user role
# ---------------------------------------------------------------------------


@company_admin_routes.patch("/users/{user_id}/role")
def change_user_role(
    body: ChangeRoleRequest,
    user_id: str = Path(..., description="User ID to update"),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.users_change_role")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Find the target user's profile within the same org
        profile = (
            session.query(UserProfile)
            .filter(
                UserProfile.user_id == user_id,
                UserProfile.org_id == org_id,
            )
            .first()
        )
        if not profile:
            return create_response(
                "User not found in your organization", False, NOT_FOUND, status_code=404
            )

        # Validate new role exists
        new_role = (
            session.query(Roles)
            .filter(
                func.lower(Roles.name) == body.role_name.lower(),
                Roles.is_deleted == False,
            )
            .first()
        )
        if not new_role:
            return create_response(
                f"Role '{body.role_name}' not found",
                False,
                VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Prevent company-admin from assigning super-admin or distributor roles
        restricted_roles = {"super-admin", "distributor"}
        if body.role_name.lower() in restricted_roles:
            return create_response(
                f"Cannot assign '{body.role_name}' role at company-admin level",
                False,
                FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        old_role_id = profile.role
        profile.role = new_role.id
        session.commit()

        logger.info(
            f"Role changed: user={user_id} old_role_id={old_role_id} "
            f"new_role={new_role.name} by={user_data.get('sub')}"
        )

        return create_response(
            "User role updated successfully", True, SUCCESS_CODE,
            data={
                "user_id": user_id,
                "new_role": new_role.name,
                "new_role_id": _serialize_uuid(new_role.id),
            },
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Error changing user role: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 9. PATCH /company-admin/users/{user_id}/deactivate — Deactivate user
# ---------------------------------------------------------------------------


@company_admin_routes.patch("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: str = Path(..., description="User ID to deactivate"),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    log_access(user_data, "company_admin.users_deactivate")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Prevent self-deactivation
        if str(user_data.get("sub")) == str(user_id):
            return create_response(
                "Cannot deactivate your own account",
                False,
                VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Find user and profile in same org
        user = (
            session.query(Users)
            .filter(Users.user_id == user_id)
            .first()
        )
        if not user:
            return create_response(
                "User not found", False, NOT_FOUND, status_code=404
            )

        profile = (
            session.query(UserProfile)
            .filter(
                UserProfile.user_id == user_id,
                UserProfile.org_id == org_id,
            )
            .first()
        )
        if not profile:
            return create_response(
                "User not found in your organization", False, NOT_FOUND, status_code=404
            )

        user.is_active = False
        profile.is_active = False
        session.commit()

        logger.info(
            f"User deactivated: user={user_id} by={user_data.get('sub')}"
        )

        return create_response(
            "User deactivated successfully", True, SUCCESS_CODE,
            data={
                "user_id": user_id,
                "is_active": False,
            },
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Error deactivating user: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 10. GET /company-admin/costs — Cost dashboard (platform + company)
# ---------------------------------------------------------------------------


@company_admin_routes.get("/costs")
def cost_dashboard(user_data: dict = Depends(require_role_or_above("company-admin"))):
    log_access(user_data, "company_admin.costs")
    session = ScopedSession()
    try:
        org_id = _org_id(user_data)
        if not org_id:
            return create_response(
                "Organization not found for user", False, NOT_FOUND, status_code=404
            )

        # Query cost records: platform-scope (org_id is null) + company-scope for this org
        costs = (
            session.query(CostRecord)
            .filter(
                CostRecord.scope.in_(["platform", "company"]),
                (CostRecord.organization_id == org_id)
                | (CostRecord.organization_id.is_(None)),
            )
            .order_by(CostRecord.period_start.desc().nullslast())
            .all()
        )

        # Build breakdowns by scope and category
        breakdowns: dict[str, dict[str, float]] = {}
        records = []
        for c in costs:
            scope = c.scope or "unknown"
            category = c.category or "uncategorized"
            amount = _serialize_decimal(c.amount) or 0

            breakdowns.setdefault(scope, {})
            breakdowns[scope][category] = breakdowns[scope].get(category, 0) + amount

            records.append({
                "id": _serialize_uuid(c.id),
                "scope": scope,
                "category": category,
                "amount": _serialize_decimal(c.amount),
                "period_start": c.period_start.isoformat() if c.period_start else None,
                "period_end": c.period_end.isoformat() if c.period_end else None,
                "description": c.description,
            })

        return create_response(
            "Cost dashboard retrieved successfully", True, SUCCESS_CODE,
            data={
                "breakdowns": breakdowns,
                "records": records,
            },
        )

    except Exception as e:
        logger.error(f"Error fetching cost dashboard: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()
