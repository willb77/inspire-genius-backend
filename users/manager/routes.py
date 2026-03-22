import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from typing import Optional

from sqlalchemy import func, cast, Date
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
)

from users.models.user import Users, UserProfile, EmployeeProfile
from users.models.rbac import Roles
from users.models.manager import (
    TrainingAssignment,
    HiringPosition,
    Candidate,
    Interview,
    InterviewStatusEnum,
)
from users.models.phase3 import UserGoal, UserActivity, CostRecord

# Attempt to import chat models for session_activity enrichment
try:
    from ai.models.chat import Conversation, ChatMessage
    _HAS_CHAT_MODELS = True
except ImportError:
    _HAS_CHAT_MODELS = False

manager_routes = APIRouter(prefix="/manager", tags=["Manager"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class MeetingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    scheduled_at: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    candidate_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_manager_profile_id(session, user_id: str):
    """Return the UserProfile.id for the authenticated manager."""
    profile = (
        session.query(UserProfile.id, UserProfile.org_id)
        .filter(UserProfile.user_id == user_id)
        .first()
    )
    return profile  # (profile_id, org_id) or None


def _get_direct_report_ids(session, manager_profile_id):
    """Return list of (user_profile_id, user_id) tuples for direct reports."""
    rows = (
        session.query(
            EmployeeProfile.user_profile_id,
            UserProfile.user_id,
        )
        .join(UserProfile, UserProfile.id == EmployeeProfile.user_profile_id)
        .filter(EmployeeProfile.manager_id == manager_profile_id)
        .all()
    )
    return rows


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
# 1. GET /manager/team — List direct reports
# ---------------------------------------------------------------------------


@manager_routes.get("/team")
def list_team(user_data: dict = Depends(require_role_or_above("manager"))):
    log_access(user_data, "manager.team")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        manager_profile_id, _ = profile
        reports = _get_direct_report_ids(session, manager_profile_id)
        if not reports:
            return create_response(
                "Team retrieved successfully", True, SUCCESS_CODE,
                data={"team": []}
            )

        team = []
        for _profile_id, report_user_id in reports:
            # User + Profile + Role
            row = (
                session.query(
                    Users.user_id,
                    Users.email,
                    UserProfile.first_name,
                    UserProfile.last_name,
                    UserProfile.is_active,
                    Roles.name.label("role_name"),
                    EmployeeProfile.department,
                    EmployeeProfile.position,
                )
                .join(UserProfile, UserProfile.user_id == Users.user_id)
                .outerjoin(Roles, Roles.id == UserProfile.role)
                .outerjoin(
                    EmployeeProfile,
                    EmployeeProfile.user_profile_id == UserProfile.id,
                )
                .filter(Users.user_id == report_user_id)
                .first()
            )
            if not row:
                continue

            # Last active
            last_activity = (
                session.query(func.max(UserActivity.created_at))
                .filter(UserActivity.user_id == report_user_id)
                .scalar()
            )

            # Goals status counts
            goal_counts = dict(
                session.query(UserGoal.status, func.count(UserGoal.id))
                .filter(
                    UserGoal.user_id == report_user_id,
                    UserGoal.is_deleted == False,
                )
                .group_by(UserGoal.status)
                .all()
            )

            # Training status counts
            training_counts = dict(
                session.query(TrainingAssignment.status, func.count(TrainingAssignment.id))
                .filter(
                    TrainingAssignment.user_id == report_user_id,
                    TrainingAssignment.is_deleted == False,
                )
                .group_by(TrainingAssignment.status)
                .all()
            )
            # Convert enum keys to strings
            training_status = {
                (k.value if hasattr(k, "value") else str(k)): v
                for k, v in training_counts.items()
            }

            team.append({
                "user_id": _serialize_uuid(row.user_id),
                "email": row.email,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "role_name": row.role_name,
                "department": row.department,
                "position": row.position,
                "is_active": row.is_active,
                "last_active": last_activity.isoformat() if last_activity else None,
                "goals_status": goal_counts,
                "training_status": training_status,
                "ig_interaction_pct": 0,
            })

        return create_response(
            "Team retrieved successfully", True, SUCCESS_CODE,
            data={"team": team}
        )

    except Exception as e:
        logger.error(f"Error listing team: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 3. GET /manager/team/health — Per-member health
# ---------------------------------------------------------------------------


@manager_routes.get("/team/health")
def team_health(user_data: dict = Depends(require_role_or_above("manager"))):
    log_access(user_data, "manager.team_health")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        manager_profile_id, _ = profile
        reports = _get_direct_report_ids(session, manager_profile_id)

        members = []
        for _profile_id, report_user_id in reports:
            up = (
                session.query(UserProfile.first_name, UserProfile.last_name)
                .filter(UserProfile.user_id == report_user_id)
                .first()
            )
            name = f"{up.first_name or ''} {up.last_name or ''}".strip() if up else "Unknown"

            # Goals completion %
            goal_total = (
                session.query(func.count(UserGoal.id))
                .filter(UserGoal.user_id == report_user_id, UserGoal.is_deleted == False)
                .scalar()
            ) or 0
            goal_completed = (
                session.query(func.count(UserGoal.id))
                .filter(
                    UserGoal.user_id == report_user_id,
                    UserGoal.is_deleted == False,
                    UserGoal.status == "completed",
                )
                .scalar()
            ) or 0
            goals_completion_pct = round(
                (goal_completed / goal_total * 100) if goal_total else 0, 1
            )

            # Training progress %
            training_rows = (
                session.query(func.avg(TrainingAssignment.progress_pct))
                .filter(
                    TrainingAssignment.user_id == report_user_id,
                    TrainingAssignment.is_deleted == False,
                )
                .scalar()
            )
            training_progress_pct = round(float(training_rows or 0), 1)

            members.append({
                "user_id": _serialize_uuid(report_user_id),
                "name": name,
                "prism_thermometer": "G",  # placeholder — Green
                "goals_completion_pct": goals_completion_pct,
                "training_progress_pct": training_progress_pct,
            })

        return create_response(
            "Team health retrieved successfully", True, SUCCESS_CODE,
            data={"members": members}
        )

    except Exception as e:
        logger.error(f"Error fetching team health: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 4. GET /manager/team/stats — Aggregated team stats
# ---------------------------------------------------------------------------


@manager_routes.get("/team/stats")
def team_stats(user_data: dict = Depends(require_role_or_above("manager"))):
    log_access(user_data, "manager.team_stats")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        manager_profile_id, _ = profile
        reports = _get_direct_report_ids(session, manager_profile_id)
        report_user_ids = [r[1] for r in reports]
        team_member_count = len(report_user_ids)

        if not report_user_ids:
            return create_response(
                "Team stats retrieved successfully", True, SUCCESS_CODE,
                data={
                    "team_member_count": 0,
                    "active_goals": 0,
                    "avg_ig_interaction_pct": 0,
                    "training_completion_rate": 0,
                    "ig_assessed_count": 0,
                },
            )

        active_goals = (
            session.query(func.count(UserGoal.id))
            .filter(
                UserGoal.user_id.in_(report_user_ids),
                UserGoal.is_deleted == False,
                UserGoal.status == "active",
            )
            .scalar()
        ) or 0

        # Training completion rate
        total_training = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(report_user_ids),
                TrainingAssignment.is_deleted == False,
            )
            .scalar()
        ) or 0
        completed_training = (
            session.query(func.count(TrainingAssignment.id))
            .filter(
                TrainingAssignment.user_id.in_(report_user_ids),
                TrainingAssignment.is_deleted == False,
                TrainingAssignment.status == "completed",
            )
            .scalar()
        ) or 0
        training_completion_rate = round(
            (completed_training / total_training * 100) if total_training else 0, 1
        )

        return create_response(
            "Team stats retrieved successfully", True, SUCCESS_CODE,
            data={
                "team_member_count": team_member_count,
                "active_goals": active_goals,
                "avg_ig_interaction_pct": 0,  # placeholder
                "training_completion_rate": training_completion_rate,
                "ig_assessed_count": 0,  # placeholder
            },
        )

    except Exception as e:
        logger.error(f"Error fetching team stats: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 5. GET /manager/team/coaching-progress — Time-series placeholder
# ---------------------------------------------------------------------------


@manager_routes.get("/team/coaching-progress")
def team_coaching_progress(
    user_data: dict = Depends(require_role_or_above("manager")),
):
    log_access(user_data, "manager.team_coaching_progress")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        manager_profile_id, _ = profile
        reports = _get_direct_report_ids(session, manager_profile_id)
        report_user_ids = [r[1] for r in reports]

        # Build last 6 months time-series
        now = datetime.now(timezone.utc)
        series = []
        for i in range(5, -1, -1):
            month_start = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            # Approximate month end
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1)

            sessions_count = 0
            goals_completed = 0
            if report_user_ids:
                sessions_count = (
                    session.query(func.count(UserActivity.id))
                    .filter(
                        UserActivity.user_id.in_(report_user_ids),
                        UserActivity.activity_type == "session",
                        UserActivity.created_at >= month_start,
                        UserActivity.created_at < month_end,
                    )
                    .scalar()
                ) or 0

                goals_completed = (
                    session.query(func.count(UserGoal.id))
                    .filter(
                        UserGoal.user_id.in_(report_user_ids),
                        UserGoal.is_deleted == False,
                        UserGoal.status == "completed",
                        UserGoal.completed_at >= month_start,
                        UserGoal.completed_at < month_end,
                    )
                    .scalar()
                ) or 0

            series.append({
                "month": month_start.strftime("%Y-%m"),
                "sessions_count": sessions_count,
                "goals_completed": goals_completed,
            })

        return create_response(
            "Coaching progress retrieved successfully", True, SUCCESS_CODE,
            data={"coaching_progress": series}
        )

    except Exception as e:
        logger.error(f"Error fetching coaching progress: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 2. GET /manager/team/{user_id} — Individual detail
#    (MUST come after /team/health, /team/stats, /team/coaching-progress)
# ---------------------------------------------------------------------------


@manager_routes.get("/team/{user_id}")
def get_team_member_detail(
    user_id: str = Path(..., description="User ID of the team member"),
    user_data: dict = Depends(require_role_or_above("manager")),
):
    log_access(user_data, "manager.team_member_detail")
    session = ScopedSession()
    try:
        manager_user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, manager_user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        manager_profile_id, _ = profile

        # Verify the requested user is a direct report
        is_report = (
            session.query(EmployeeProfile.id)
            .join(UserProfile, UserProfile.id == EmployeeProfile.user_profile_id)
            .filter(
                UserProfile.user_id == user_id,
                EmployeeProfile.manager_id == manager_profile_id,
            )
            .first()
        )
        if not is_report:
            return create_response(
                "User is not a direct report", False, NOT_FOUND, status_code=404
            )

        # Basic info
        row = (
            session.query(
                Users.user_id,
                Users.email,
                UserProfile.first_name,
                UserProfile.last_name,
                UserProfile.is_active,
                Roles.name.label("role_name"),
                EmployeeProfile.department,
                EmployeeProfile.position,
                EmployeeProfile.hire_date,
            )
            .join(UserProfile, UserProfile.user_id == Users.user_id)
            .outerjoin(Roles, Roles.id == UserProfile.role)
            .outerjoin(
                EmployeeProfile,
                EmployeeProfile.user_profile_id == UserProfile.id,
            )
            .filter(Users.user_id == user_id)
            .first()
        )
        if not row:
            return create_response(
                "User not found", False, NOT_FOUND, status_code=404
            )

        user_info = {
            "user_id": _serialize_uuid(row.user_id),
            "email": row.email,
            "first_name": row.first_name,
            "last_name": row.last_name,
            "is_active": row.is_active,
            "role_name": row.role_name,
            "department": row.department,
            "position": row.position,
            "hire_date": row.hire_date.isoformat() if row.hire_date else None,
        }

        # Coaching history — recent sessions from UserActivity
        coaching_rows = (
            session.query(UserActivity)
            .filter(
                UserActivity.user_id == user_id,
                UserActivity.activity_type == "session",
            )
            .order_by(UserActivity.created_at.desc())
            .limit(20)
            .all()
        )
        coaching_history = [
            {
                "id": _serialize_uuid(a.id),
                "description": a.description,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in coaching_rows
        ]

        # Session activity from chat models (if available)
        session_activity = None
        if _HAS_CHAT_MODELS:
            try:
                convo_count = (
                    session.query(func.count(Conversation.id))
                    .filter(Conversation.user_id == user_id)
                    .scalar()
                ) or 0
                msg_count = (
                    session.query(func.count(ChatMessage.id))
                    .join(Conversation, Conversation.id == ChatMessage.conversation_id)
                    .filter(Conversation.user_id == user_id)
                    .scalar()
                ) or 0
                session_activity = {
                    "conversation_count": convo_count,
                    "message_count": msg_count,
                }
            except Exception:
                session_activity = None

        return create_response(
            "Team member detail retrieved successfully", True, SUCCESS_CODE,
            data={
                "user": user_info,
                "coaching_history": coaching_history,
                "prism_profile": None,  # placeholder
                "session_activity": session_activity,
            },
        )

    except Exception as e:
        logger.error(f"Error fetching team member detail: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 6. GET /manager/hiring/pipeline — Hiring pipeline
# ---------------------------------------------------------------------------


@manager_routes.get("/hiring/pipeline")
def hiring_pipeline(user_data: dict = Depends(require_role_or_above("manager"))):
    log_access(user_data, "manager.hiring_pipeline")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")

        positions = (
            session.query(HiringPosition)
            .options(
                joinedload(HiringPosition.candidates).joinedload(Candidate.interviews)
            )
            .filter(
                HiringPosition.manager_id == user_id,
                HiringPosition.is_deleted == False,
            )
            .all()
        )

        pipeline = []
        upcoming_interviews = []
        now = datetime.now(timezone.utc)

        for pos in positions:
            # Count candidates by stage
            stage_counts: dict[str, int] = {}
            for c in pos.candidates:
                if c.is_deleted:
                    continue
                stage = c.status.value if hasattr(c.status, "value") else str(c.status)
                stage_counts[stage] = stage_counts.get(stage, 0) + 1

                # Collect upcoming interviews
                for iv in (c.interviews or []):
                    if iv.is_deleted:
                        continue
                    if (
                        iv.status == InterviewStatusEnum.SCHEDULED
                        and iv.scheduled_at
                        and iv.scheduled_at >= now
                    ):
                        upcoming_interviews.append({
                            "interview_id": _serialize_uuid(iv.id),
                            "position_title": pos.title,
                            "candidate_name": c.name,
                            "scheduled_at": iv.scheduled_at.isoformat(),
                            "duration_minutes": iv.duration_minutes,
                            "location": iv.location,
                            "meeting_url": iv.meeting_url,
                        })

            pipeline.append({
                "position_id": _serialize_uuid(pos.id),
                "title": pos.title,
                "department": pos.department,
                "status": pos.status.value if hasattr(pos.status, "value") else str(pos.status),
                "candidate_count": sum(stage_counts.values()),
                "candidates_by_stage": stage_counts,
                "created_at": pos.created_at.isoformat() if pos.created_at else None,
            })

        # Sort upcoming interviews by date
        upcoming_interviews.sort(key=lambda x: x["scheduled_at"])

        return create_response(
            "Hiring pipeline retrieved successfully", True, SUCCESS_CODE,
            data={
                "positions": pipeline,
                "upcoming_interviews": upcoming_interviews[:20],
            },
        )

    except Exception as e:
        logger.error(f"Error fetching hiring pipeline: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 7. POST /manager/meetings/create — Create a meeting
# ---------------------------------------------------------------------------


@manager_routes.post("/meetings/create")
def create_meeting(
    body: MeetingCreateRequest,
    user_data: dict = Depends(require_role_or_above("manager")),
):
    log_access(user_data, "manager.meetings_create")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        meeting_id = uuid.uuid4()
        meeting_url = f"https://meet.google.com/placeholder-{meeting_id}"

        # If candidate_id is provided, create an Interview record
        if body.candidate_id:
            candidate = (
                session.query(Candidate)
                .filter(
                    Candidate.id == body.candidate_id,
                    Candidate.is_deleted == False,
                )
                .first()
            )
            if not candidate:
                return create_response(
                    "Candidate not found", False, NOT_FOUND, status_code=404
                )

            interview = Interview(
                id=meeting_id,
                candidate_id=candidate.id,
                interviewer_id=user_id,
                scheduled_at=body.scheduled_at,
                duration_minutes=body.duration_minutes,
                meeting_url=meeting_url,
                status=InterviewStatusEnum.SCHEDULED,
            )
            session.add(interview)
            session.commit()

            logger.info(
                f"Meeting created: id={meeting_id} candidate={body.candidate_id} "
                f"by manager={user_id}"
            )
        else:
            # Log a generic meeting (no DB record for non-candidate meetings)
            logger.info(
                f"Generic meeting created: title='{body.title}' "
                f"scheduled_at={body.scheduled_at} by manager={user_id}"
            )

        return create_response(
            "Meeting created successfully", True, SUCCESS_CODE,
            data={
                "meeting_id": str(meeting_id),
                "title": body.title,
                "scheduled_at": body.scheduled_at.isoformat(),
                "duration_minutes": body.duration_minutes,
                "meeting_url": meeting_url,
                "candidate_id": body.candidate_id,
            },
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating meeting: {e}")
        return create_response(
            "Something went wrong", False, SOMETHING_WENT_WRONG, status_code=500
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 8. GET /manager/costs — Cost dashboard scoped to team
# ---------------------------------------------------------------------------


@manager_routes.get("/costs")
def cost_dashboard(user_data: dict = Depends(require_role_or_above("manager"))):
    log_access(user_data, "manager.costs")
    session = ScopedSession()
    try:
        user_id = user_data.get("sub")
        profile = _get_manager_profile_id(session, user_id)
        if not profile:
            return create_response(
                "Manager profile not found", False, NOT_FOUND, status_code=404
            )

        _, org_id = profile

        # Query cost records for team / company / platform scopes matching org
        cost_filter = CostRecord.scope.in_(["team", "company", "platform"])
        if org_id:
            costs = (
                session.query(CostRecord)
                .filter(
                    cost_filter,
                    (CostRecord.organization_id == org_id)
                    | (CostRecord.organization_id.is_(None)),
                )
                .order_by(CostRecord.period_start.desc().nullslast())
                .all()
            )
        else:
            costs = (
                session.query(CostRecord)
                .filter(cost_filter)
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
