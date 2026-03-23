from fastapi import APIRouter, Depends, Query
from typing import Optional

from sqlalchemy import func

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_authenticated_user
from users.models.user import Users, UserProfile
from users.models.phase3 import UserGoal, UserActivity, CostRecord
from users.models.manager import TrainingAssignment, TrainingStatusEnum
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
)

user_dashboard_routes = APIRouter(prefix="/user", tags=["User Dashboard"])


@user_dashboard_routes.get("/dashboard/stats")
def get_dashboard_stats(
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return aggregated dashboard statistics for the current user."""
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")

        # Session count
        total_sessions = (
            session.query(func.count(UserActivity.id))
            .filter(
                UserActivity.user_id == user_id,
                UserActivity.activity_type == "session",
            )
            .scalar()
            or 0
        )

        # Goal counts by status
        completed_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id == user_id,
                UserGoal.status == "completed",
                UserGoal.is_deleted == False,
            )
            .scalar()
            or 0
        )
        active_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id == user_id,
                UserGoal.status == "active",
                UserGoal.is_deleted == False,
            )
            .scalar()
            or 0
        )
        pending_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id == user_id,
                UserGoal.status == "pending",
                UserGoal.is_deleted == False,
            )
            .scalar()
            or 0
        )

        # Training counts
        training_assigned = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
            or 0
        )
        training_completion = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.status == TrainingStatusEnum.COMPLETED,
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
            or 0
        )

        return create_response(
            message="Dashboard stats retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_sessions": total_sessions,
                "completed_goals": completed_goals,
                "active_goals": active_goals,
                "pending_goals": pending_goals,
                "ig_interaction_pct": 0,
                "training_completion": training_completion,
                "training_assigned": training_assigned,
                "ig_assessment_status": "not_assessed",
            },
        )
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {str(e)}")
        return create_response(
            message="Failed to retrieve dashboard stats",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@user_dashboard_routes.get("/dashboard/activity")
def get_user_activity(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return paginated activity log for the current user."""
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        offset = (page - 1) * limit

        total = (
            session.query(func.count(UserActivity.id))
            .filter(UserActivity.user_id == user_id)
            .scalar()
            or 0
        )

        activities = (
            session.query(UserActivity)
            .filter(UserActivity.user_id == user_id)
            .order_by(UserActivity.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        activity_list = [
            {
                "id": str(a.id),
                "activity_type": a.activity_type,
                "description": a.description,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ]

        return create_response(
            message="Activity log retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "activities": activity_list,
                "page": page,
                "limit": limit,
                "total": total,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching user activity: {str(e)}")
        return create_response(
            message="Failed to retrieve activity log",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@user_dashboard_routes.get("/costs")
def get_user_costs(
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return cost records scoped to the current user."""
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")

        records = (
            session.query(CostRecord)
            .filter(
                CostRecord.scope == "user",
                CostRecord.user_id == user_id,
            )
            .order_by(CostRecord.created_at.desc())
            .all()
        )

        cost_list = [
            {
                "id": str(r.id),
                "scope": r.scope,
                "category": r.category,
                "amount": float(r.amount) if r.amount is not None else None,
                "period_start": r.period_start.isoformat() if r.period_start else None,
                "period_end": r.period_end.isoformat() if r.period_end else None,
                "description": r.description,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        return create_response(
            message="User cost records retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"costs": cost_list},
        )
    except Exception as e:
        logger.error(f"Error fetching user costs: {str(e)}")
        return create_response(
            message="Failed to retrieve cost records",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@user_dashboard_routes.get("/goals")
def get_user_goals(
    status: Optional[str] = Query(None),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return goals for the current user, optionally filtered by status."""
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")

        query = session.query(UserGoal).filter(
            UserGoal.user_id == user_id,
            UserGoal.is_deleted == False,
        )

        if status:
            query = query.filter(UserGoal.status == status)

        goals = query.order_by(UserGoal.created_at.desc()).all()

        goal_list = [
            {
                "id": str(g.id),
                "title": g.title,
                "description": g.description,
                "status": g.status,
                "due_date": g.due_date.isoformat() if g.due_date else None,
                "progress_pct": g.progress_pct,
                "completed_at": g.completed_at.isoformat() if g.completed_at else None,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in goals
        ]

        return create_response(
            message="User goals retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"goals": goal_list},
        )
    except Exception as e:
        logger.error(f"Error fetching user goals: {str(e)}")
        return create_response(
            message="Failed to retrieve goals",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@user_dashboard_routes.get("/training")
def get_user_training(
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return training assignments for the current user."""
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")

        assignments = (
            session.query(TrainingAssignment)
            .filter(
                TrainingAssignment.user_id == user_id,
                TrainingAssignment.is_deleted == False,
            )
            .order_by(TrainingAssignment.created_at.desc())
            .all()
        )

        training_list = [
            {
                "id": str(t.id),
                "title": t.title,
                "description": t.description,
                "status": t.status.value if t.status else None,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "progress_pct": t.progress_pct,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in assignments
        ]

        return create_response(
            message="Training assignments retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"training": training_list},
        )
    except Exception as e:
        logger.error(f"Error fetching user training: {str(e)}")
        return create_response(
            message="Failed to retrieve training assignments",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
