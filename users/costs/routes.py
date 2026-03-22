from fastapi import APIRouter, Depends, Query
from datetime import date

from sqlalchemy import func, extract

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_authenticated_user, log_access, role_rank
from users.models.phase3 import CostRecord
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    FORBIDDEN_ERROR_CODE,
    VALIDATION_ERROR_CODE,
)

cost_routes = APIRouter(prefix="/costs", tags=["Cost Dashboard"])

VALID_SCOPES = {"platform", "company", "team", "user"}

# Minimum role_rank required for each scope
SCOPE_MIN_RANK = {
    "platform": 5,   # super-admin
    "company": 2,    # company-admin or above
    "team": 1,       # manager or above
    "user": 0,       # any authenticated user
}


def _check_scope_access(user_data: dict, scope: str) -> str | None:
    """Return an error message if the user lacks access for the given scope, else None."""
    user_role = (user_data.get("user_role") or "user").lower()
    user_rank = role_rank(user_role)
    required_rank = SCOPE_MIN_RANK.get(scope, 999)
    if user_rank < required_rank:
        return (
            f"Access denied - scope '{scope}' requires role rank >= {required_rank}, "
            f"current role '{user_role}' has rank {user_rank}"
        )
    return None


def _apply_scope_filters(query, scope: str, user_data: dict):
    """Apply scope-based filters to a CostRecord query."""
    query = query.filter(CostRecord.scope == scope)

    if scope in ("company", "team"):
        role_info = user_data.get("role_info", {})
        org_id = role_info.get("organization_id") if isinstance(role_info, dict) else None
        if org_id:
            query = query.filter(CostRecord.organization_id == org_id)
    elif scope == "user":
        user_id = user_data.get("sub")
        query = query.filter(CostRecord.user_id == user_id)

    return query


def _build_dashboard_data(session, query):
    """Build the standard cost dashboard payload from a filtered query."""
    # Total cost
    total_cost = (
        session.query(func.sum(CostRecord.amount))
        .filter(CostRecord.id.in_(query.with_entities(CostRecord.id).subquery().select()))
        .scalar()
    )

    # Breakdown by category
    category_rows = (
        query.with_entities(
            CostRecord.category,
            func.sum(CostRecord.amount).label("total"),
        )
        .group_by(CostRecord.category)
        .all()
    )
    breakdown_by_category = [
        {
            "category": row.category,
            "total": float(row.total) if row.total is not None else 0,
        }
        for row in category_rows
    ]

    # Time series
    time_rows = (
        query.with_entities(
            CostRecord.period_start,
            func.sum(CostRecord.amount).label("total"),
        )
        .group_by(CostRecord.period_start)
        .order_by(CostRecord.period_start)
        .all()
    )
    time_series = [
        {
            "period_start": row.period_start.isoformat() if row.period_start else None,
            "total": float(row.total) if row.total is not None else 0,
        }
        for row in time_rows
    ]

    return {
        "total_cost": float(total_cost) if total_cost is not None else 0,
        "breakdown_by_category": breakdown_by_category,
        "time_series": time_series,
        "comparison_metrics": {},
    }


@cost_routes.get("/dashboard")
def get_cost_dashboard(
    scope: str = Query(..., description="One of: platform, company, team, user"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return cost dashboard data for the requested scope."""
    if scope not in VALID_SCOPES:
        return create_response(
            message=f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    access_error = _check_scope_access(user_data, scope)
    if access_error:
        log_access(user_data, "cost_dashboard", action=f"denied:{scope}")
        return create_response(
            message=access_error,
            status=False,
            error_code=FORBIDDEN_ERROR_CODE,
            status_code=403,
        )

    session = ScopedSession()
    try:
        log_access(user_data, "cost_dashboard", action=f"read:{scope}")

        query = _apply_scope_filters(session.query(CostRecord), scope, user_data)
        data = _build_dashboard_data(session, query)

        return create_response(
            message="Cost dashboard retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data=data,
        )
    except Exception as e:
        logger.error(f"Error fetching cost dashboard: {str(e)}")
        return create_response(
            message="Failed to retrieve cost dashboard",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@cost_routes.get("/dashboard/filter")
def get_cost_dashboard_filtered(
    start_date: str = Query(..., description="ISO date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="ISO date (YYYY-MM-DD)"),
    period: str = Query(..., description="One of: day, month, range"),
    scope: str = Query(..., description="One of: platform, company, team, user"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return filtered cost dashboard data with date range and grouping."""
    if scope not in VALID_SCOPES:
        return create_response(
            message=f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    if period not in ("day", "month", "range"):
        return create_response(
            message="Invalid period. Must be one of: day, month, range",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    # Parse dates
    try:
        parsed_start = date.fromisoformat(start_date)
        parsed_end = date.fromisoformat(end_date)
    except ValueError:
        return create_response(
            message="Invalid date format. Use ISO format (YYYY-MM-DD)",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    access_error = _check_scope_access(user_data, scope)
    if access_error:
        log_access(user_data, "cost_dashboard_filter", action=f"denied:{scope}")
        return create_response(
            message=access_error,
            status=False,
            error_code=FORBIDDEN_ERROR_CODE,
            status_code=403,
        )

    session = ScopedSession()
    try:
        log_access(user_data, "cost_dashboard_filter", action=f"read:{scope}")

        query = _apply_scope_filters(session.query(CostRecord), scope, user_data)
        query = query.filter(
            CostRecord.period_start >= parsed_start,
            CostRecord.period_end <= parsed_end,
        )

        # Total cost
        total_cost_val = (
            session.query(func.sum(CostRecord.amount))
            .filter(
                CostRecord.id.in_(
                    query.with_entities(CostRecord.id).subquery().select()
                )
            )
            .scalar()
        )

        # Breakdown by category
        category_rows = (
            query.with_entities(
                CostRecord.category,
                func.sum(CostRecord.amount).label("total"),
            )
            .group_by(CostRecord.category)
            .all()
        )
        breakdown_by_category = [
            {
                "category": row.category,
                "total": float(row.total) if row.total is not None else 0,
            }
            for row in category_rows
        ]

        # Time series grouped by period
        if period == "day":
            time_rows = (
                query.with_entities(
                    CostRecord.period_start,
                    func.sum(CostRecord.amount).label("total"),
                )
                .group_by(CostRecord.period_start)
                .order_by(CostRecord.period_start)
                .all()
            )
            time_series = [
                {
                    "period_start": row.period_start.isoformat()
                    if row.period_start
                    else None,
                    "total": float(row.total) if row.total is not None else 0,
                }
                for row in time_rows
            ]
        elif period == "month":
            time_rows = (
                query.with_entities(
                    extract("year", CostRecord.period_start).label("yr"),
                    extract("month", CostRecord.period_start).label("mo"),
                    func.sum(CostRecord.amount).label("total"),
                )
                .group_by("yr", "mo")
                .order_by("yr", "mo")
                .all()
            )
            time_series = [
                {
                    "year": int(row.yr) if row.yr else None,
                    "month": int(row.mo) if row.mo else None,
                    "total": float(row.total) if row.total is not None else 0,
                }
                for row in time_rows
            ]
        else:
            # "range" — single aggregate over the whole date range
            agg_total = (
                session.query(func.sum(CostRecord.amount))
                .filter(
                    CostRecord.id.in_(
                        query.with_entities(CostRecord.id).subquery().select()
                    )
                )
                .scalar()
            )
            time_series = [
                {
                    "period_start": parsed_start.isoformat(),
                    "period_end": parsed_end.isoformat(),
                    "total": float(agg_total) if agg_total is not None else 0,
                }
            ]

        return create_response(
            message="Filtered cost data retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_cost": float(total_cost_val) if total_cost_val is not None else 0,
                "breakdown_by_category": breakdown_by_category,
                "time_series": time_series,
                "comparison_metrics": {},
            },
        )
    except Exception as e:
        logger.error(f"Error fetching filtered cost dashboard: {str(e)}")
        return create_response(
            message="Failed to retrieve filtered cost data",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
