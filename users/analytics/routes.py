from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, extract

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import (
    require_authenticated_user,
    require_role_or_above,
    require_role,
    log_access,
    role_rank,
)
from users.models.phase3 import UserGoal, UserActivity
from users.models.manager import TrainingAssignment
from users.models.user import (
    Users,
    UserProfile,
    EmployeeProfile,
    Organization,
)
from users.models.feedback import Feedback
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
)

analytics_routes = APIRouter(prefix="/analytics", tags=["Analytics"])

VALID_GRANULARITIES = {"day", "week", "month"}


def _parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple[date, date]:
    """Return (start, end) dates; defaults to last 6 months if not provided."""
    today = date.today()
    if end_date:
        try:
            parsed_end = date.fromisoformat(end_date)
        except ValueError:
            parsed_end = today
    else:
        parsed_end = today

    if start_date:
        try:
            parsed_start = date.fromisoformat(start_date)
        except ValueError:
            parsed_start = parsed_end - timedelta(days=180)
    else:
        parsed_start = parsed_end - timedelta(days=180)

    return parsed_start, parsed_end


def _build_time_series(
    session,
    model_class,
    date_column,
    filter_conditions: list,
    granularity: str,
    start: date,
    end: date,
) -> list[dict]:
    """Build grouped time-series data from a model."""
    col = getattr(model_class, date_column)
    base_q = session.query(col).filter(
        col >= start,
        col <= end,
        *filter_conditions,
    )

    if granularity == "day":
        rows = (
            session.query(
                func.date(col).label("period"),
                func.count().label("count"),
            )
            .filter(col >= start, col <= end, *filter_conditions)
            .group_by(func.date(col))
            .order_by(func.date(col))
            .all()
        )
        return [
            {"period": str(r.period), "count": r.count}
            for r in rows
        ]
    elif granularity == "week":
        rows = (
            session.query(
                extract("isoyear", col).label("yr"),
                extract("week", col).label("wk"),
                func.count().label("count"),
            )
            .filter(col >= start, col <= end, *filter_conditions)
            .group_by("yr", "wk")
            .order_by("yr", "wk")
            .all()
        )
        return [
            {"period": f"{int(r.yr)}-W{int(r.wk):02d}", "count": r.count}
            for r in rows
        ]
    else:  # month
        rows = (
            session.query(
                extract("year", col).label("yr"),
                extract("month", col).label("mo"),
                func.count().label("count"),
            )
            .filter(col >= start, col <= end, *filter_conditions)
            .group_by("yr", "mo")
            .order_by("yr", "mo")
            .all()
        )
        return [
            {"period": f"{int(r.yr)}-{int(r.mo):02d}", "count": r.count}
            for r in rows
        ]


# ── 5.C1-1  Personal user analytics ─────────────────────────────────
@analytics_routes.get("/user")
def get_user_analytics(
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    granularity: str = Query("month", description="day / week / month"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Personal analytics: sessions, goals, training progress."""
    if granularity not in VALID_GRANULARITIES:
        return create_response(
            message=f"Invalid granularity '{granularity}'. Must be one of: {', '.join(sorted(VALID_GRANULARITIES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_user", action="read")

        # Total sessions
        total_sessions = (
            session.query(func.count(UserActivity.id))
            .filter(
                UserActivity.user_id == user_id,
                UserActivity.activity_type == "session",
                UserActivity.created_at >= parsed_start,
                UserActivity.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Goals by status
        goal_rows = (
            session.query(
                UserGoal.status,
                func.count(UserGoal.id).label("count"),
            )
            .filter(
                UserGoal.user_id == user_id,
                UserGoal.is_deleted == False,
                UserGoal.created_at >= parsed_start,
                UserGoal.created_at <= parsed_end,
            )
            .group_by(UserGoal.status)
            .all()
        )
        goals_by_status = {r.status: r.count for r in goal_rows}

        # Session trends
        session_trends = _build_time_series(
            session,
            UserActivity,
            "created_at",
            [UserActivity.user_id == user_id, UserActivity.activity_type == "session"],
            granularity,
            parsed_start,
            parsed_end,
        )

        # Training progress
        training_total = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
        ) or 0
        training_completed = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.is_deleted == False,
                TrainingAssignment.status == "completed",
            )
            .scalar()
        ) or 0

        return create_response(
            message="User analytics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_sessions": total_sessions,
                "goals_by_status": goals_by_status,
                "session_trends": session_trends,
                "training": {
                    "total": training_total,
                    "completed": training_completed,
                    "completion_pct": round(
                        (training_completed / training_total * 100) if training_total else 0, 1
                    ),
                },
                "date_range": {
                    "start": parsed_start.isoformat(),
                    "end": parsed_end.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.error(f"Error fetching user analytics: {str(e)}")
        return create_response(
            message="Failed to retrieve user analytics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C1-2  Manager team analytics ──────────────────────────────────
@analytics_routes.get("/manager/team")
def get_manager_team_analytics(
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    granularity: str = Query("month", description="day / week / month"),
    user_data: dict = Depends(require_role_or_above("manager")),
):
    """Team metrics for managers: aggregate goals, sessions, training across direct reports."""
    if granularity not in VALID_GRANULARITIES:
        return create_response(
            message=f"Invalid granularity '{granularity}'. Must be one of: {', '.join(sorted(VALID_GRANULARITIES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_manager_team", action="read")

        # Find manager's UserProfile.id to match EmployeeProfile.manager_id
        manager_profile = (
            session.query(UserProfile.id)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        manager_profile_id = manager_profile.id if manager_profile else None

        # Direct report user_ids
        if manager_profile_id:
            report_rows = (
                session.query(UserProfile.user_id)
                .join(EmployeeProfile, EmployeeProfile.user_profile_id == UserProfile.id)
                .filter(EmployeeProfile.manager_id == manager_profile_id)
                .all()
            )
            report_user_ids = [r.user_id for r in report_rows]
        else:
            report_user_ids = []

        team_size = len(report_user_ids)

        if not report_user_ids:
            return create_response(
                message="Team analytics retrieved successfully",
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "team_size": 0,
                    "total_goals": 0,
                    "avg_goal_completion_pct": 0,
                    "total_sessions": 0,
                    "training": {"total": 0, "completed": 0, "completion_pct": 0},
                    "team_activity_trends": [],
                    "date_range": {
                        "start": parsed_start.isoformat(),
                        "end": parsed_end.isoformat(),
                    },
                },
            )

        # Total goals across team
        total_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id.in_(report_user_ids),
                UserGoal.is_deleted == False,
                UserGoal.created_at >= parsed_start,
                UserGoal.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Avg completion %
        avg_completion = (
            session.query(func.avg(UserGoal.progress_pct))
            .filter(
                UserGoal.user_id.in_(report_user_ids),
                UserGoal.is_deleted == False,
                UserGoal.created_at >= parsed_start,
                UserGoal.created_at <= parsed_end,
            )
            .scalar()
        )
        avg_goal_completion_pct = round(float(avg_completion), 1) if avg_completion else 0

        # Total sessions
        total_sessions = (
            session.query(func.count(UserActivity.id))
            .filter(
                UserActivity.user_id.in_(report_user_ids),
                UserActivity.activity_type == "session",
                UserActivity.created_at >= parsed_start,
                UserActivity.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Training stats
        training_total = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(report_user_ids),
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
        ) or 0
        training_completed = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(report_user_ids),
                TrainingAssignment.is_deleted == False,
                TrainingAssignment.status == "completed",
            )
            .scalar()
        ) or 0

        # Team activity time series
        team_activity_trends = _build_time_series(
            session,
            UserActivity,
            "created_at",
            [UserActivity.user_id.in_(report_user_ids)],
            granularity,
            parsed_start,
            parsed_end,
        )

        return create_response(
            message="Team analytics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "team_size": team_size,
                "total_goals": total_goals,
                "avg_goal_completion_pct": avg_goal_completion_pct,
                "total_sessions": total_sessions,
                "training": {
                    "total": training_total,
                    "completed": training_completed,
                    "completion_pct": round(
                        (training_completed / training_total * 100) if training_total else 0, 1
                    ),
                },
                "team_activity_trends": team_activity_trends,
                "date_range": {
                    "start": parsed_start.isoformat(),
                    "end": parsed_end.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.error(f"Error fetching manager team analytics: {str(e)}")
        return create_response(
            message="Failed to retrieve team analytics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C1-3  Company-wide analytics ──────────────────────────────────
@analytics_routes.get("/company")
def get_company_analytics(
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    granularity: str = Query("month", description="day / week / month"),
    user_data: dict = Depends(require_role_or_above("company-admin")),
):
    """Organization-wide analytics: users, goals, sessions, training, department breakdown."""
    if granularity not in VALID_GRANULARITIES:
        return create_response(
            message=f"Invalid granularity '{granularity}'. Must be one of: {', '.join(sorted(VALID_GRANULARITIES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)
    role_info = user_data.get("role_info", {})
    org_id = role_info.get("organization_id") if isinstance(role_info, dict) else None

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_company", action="read")

        # All user_ids in the organization
        org_user_rows = (
            session.query(UserProfile.user_id)
            .filter(UserProfile.org_id == org_id)
            .all()
        ) if org_id else []
        org_user_ids = [r.user_id for r in org_user_rows]

        total_users = len(org_user_ids)

        if not org_user_ids:
            return create_response(
                message="Company analytics retrieved successfully",
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "total_users": 0,
                    "total_goals": 0,
                    "total_sessions": 0,
                    "training": {"total": 0, "completed": 0, "completion_pct": 0},
                    "department_breakdown": [],
                    "activity_trends": [],
                    "date_range": {
                        "start": parsed_start.isoformat(),
                        "end": parsed_end.isoformat(),
                    },
                },
            )

        # Goals
        total_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id.in_(org_user_ids),
                UserGoal.is_deleted == False,
                UserGoal.created_at >= parsed_start,
                UserGoal.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Sessions
        total_sessions = (
            session.query(func.count(UserActivity.id))
            .filter(
                UserActivity.user_id.in_(org_user_ids),
                UserActivity.activity_type == "session",
                UserActivity.created_at >= parsed_start,
                UserActivity.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Training
        training_total = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(org_user_ids),
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
        ) or 0
        training_completed = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(org_user_ids),
                TrainingAssignment.is_deleted == False,
                TrainingAssignment.status == "completed",
            )
            .scalar()
        ) or 0

        # Department breakdown
        dept_rows = (
            session.query(
                EmployeeProfile.department,
                func.count(EmployeeProfile.id).label("count"),
            )
            .join(UserProfile, EmployeeProfile.user_profile_id == UserProfile.id)
            .filter(UserProfile.org_id == org_id)
            .group_by(EmployeeProfile.department)
            .all()
        )
        department_breakdown = [
            {"department": r.department or "Unassigned", "user_count": r.count}
            for r in dept_rows
        ]

        # Activity trends
        activity_trends = _build_time_series(
            session,
            UserActivity,
            "created_at",
            [UserActivity.user_id.in_(org_user_ids)],
            granularity,
            parsed_start,
            parsed_end,
        )

        return create_response(
            message="Company analytics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_users": total_users,
                "total_goals": total_goals,
                "total_sessions": total_sessions,
                "training": {
                    "total": training_total,
                    "completed": training_completed,
                    "completion_pct": round(
                        (training_completed / training_total * 100) if training_total else 0, 1
                    ),
                },
                "department_breakdown": department_breakdown,
                "activity_trends": activity_trends,
                "date_range": {
                    "start": parsed_start.isoformat(),
                    "end": parsed_end.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.error(f"Error fetching company analytics: {str(e)}")
        return create_response(
            message="Failed to retrieve company analytics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C1-4  Platform-wide analytics ─────────────────────────────────
@analytics_routes.get("/platform")
def get_platform_analytics(
    start_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD)"),
    granularity: str = Query("month", description="day / week / month"),
    user_data: dict = Depends(require_role("super-admin")),
):
    """Platform-wide analytics: total users, orgs, sessions, goals, feedback."""
    if granularity not in VALID_GRANULARITIES:
        return create_response(
            message=f"Invalid granularity '{granularity}'. Must be one of: {', '.join(sorted(VALID_GRANULARITIES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    parsed_start, parsed_end = _parse_date_range(start_date, end_date)

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_platform", action="read")

        total_users = session.query(func.count(Users.user_id)).scalar() or 0
        total_orgs = session.query(func.count(Organization.id)).scalar() or 0

        total_sessions = (
            session.query(func.count(UserActivity.id))
            .filter(
                UserActivity.activity_type == "session",
                UserActivity.created_at >= parsed_start,
                UserActivity.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        total_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.is_deleted == False,
                UserGoal.created_at >= parsed_start,
                UserGoal.created_at <= parsed_end,
            )
            .scalar()
        ) or 0

        # Feedback stats
        total_feedback = (
            session.query(func.count(Feedback.id))
            .filter(
                Feedback.is_deleted == False,
                Feedback.created_at >= parsed_start,
                Feedback.created_at <= parsed_end,
            )
            .scalar()
        ) or 0
        feedback_type_rows = (
            session.query(
                Feedback.feedback_type,
                func.count(Feedback.id).label("count"),
            )
            .filter(
                Feedback.is_deleted == False,
                Feedback.created_at >= parsed_start,
                Feedback.created_at <= parsed_end,
            )
            .group_by(Feedback.feedback_type)
            .all()
        )
        feedback_by_type = {r.feedback_type: r.count for r in feedback_type_rows}

        avg_rating = (
            session.query(func.avg(Feedback.rating))
            .filter(
                Feedback.is_deleted == False,
                Feedback.rating.isnot(None),
                Feedback.created_at >= parsed_start,
                Feedback.created_at <= parsed_end,
            )
            .scalar()
        )

        # Activity trends
        activity_trends = _build_time_series(
            session,
            UserActivity,
            "created_at",
            [],
            granularity,
            parsed_start,
            parsed_end,
        )

        return create_response(
            message="Platform analytics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_users": total_users,
                "total_organizations": total_orgs,
                "total_sessions": total_sessions,
                "total_goals": total_goals,
                "feedback": {
                    "total": total_feedback,
                    "by_type": feedback_by_type,
                    "avg_rating": round(float(avg_rating), 2) if avg_rating else None,
                },
                "activity_trends": activity_trends,
                "date_range": {
                    "start": parsed_start.isoformat(),
                    "end": parsed_end.isoformat(),
                },
            },
        )
    except Exception as e:
        logger.error(f"Error fetching platform analytics: {str(e)}")
        return create_response(
            message="Failed to retrieve platform analytics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
