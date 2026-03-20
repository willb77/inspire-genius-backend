"""
Manager API endpoints (2.1)

All endpoints require the 'manager' role.
Prefix: /v1/managers
"""
import uuid
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, Path, Query
from typing import Optional

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role
from users.response import (
    create_response, SUCCESS_CODE, SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE, NOT_FOUND,
)
from users.models.user import Users, UserProfile, EmployeeProfile
from users.models.rbac import Roles
from users.models.manager import (
    TrainingAssignment, TrainingStatusEnum,
    HiringPosition, Candidate, Interview, InterviewStatusEnum,
)
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, func, cast, Date

manager_routes = APIRouter(prefix="/managers", tags=["Manager"])

# ---------------------------------------------------------------------------
#  GET /managers/:id/team
# ---------------------------------------------------------------------------

@manager_routes.get("/{manager_id}/team")
def get_team(
    manager_id: str = Path(...),
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """List direct reports with PRISM scores and status."""
    session = ScopedSession()
    try:
        # Find team members whose EmployeeProfile.manager_id matches manager's profile
        manager_profile = session.query(UserProfile).filter(
            UserProfile.user_id == manager_id
        ).first()
        if not manager_profile:
            return create_response("Manager profile not found", False, NOT_FOUND, status_code=404)

        employees = (
            session.query(EmployeeProfile)
            .options(joinedload(EmployeeProfile.user_profile))
            .filter(EmployeeProfile.manager_id == manager_profile.id)
            .all()
        )

        team = []
        for emp in employees:
            profile = emp.user_profile
            user = session.query(Users).filter(Users.user_id == profile.user_id).first() if profile else None
            role = session.query(Roles).filter(Roles.id == profile.role).first() if profile and profile.role else None
            team.append({
                "user_id": str(profile.user_id) if profile else None,
                "email": user.email if user else None,
                "first_name": profile.first_name if profile else None,
                "last_name": profile.last_name if profile else None,
                "department": emp.department,
                "position": emp.position,
                "hire_date": emp.hire_date.isoformat() if emp.hire_date else None,
                "role": role.name if role else None,
                "is_active": profile.is_active if profile else False,
                "prism_score": None,  # placeholder — populated when PRISM integration lands
            })

        return create_response("Team retrieved", True, SUCCESS_CODE, data={"team": team, "count": len(team)})
    except Exception as e:
        logger.error(f"Error getting team: {e}")
        return create_response("Failed to retrieve team", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /managers/:id/team/:userId/activity
# ---------------------------------------------------------------------------

@manager_routes.get("/{manager_id}/team/{user_id}/activity")
def get_user_activity(
    manager_id: str = Path(...),
    user_id: str = Path(...),
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """User's IG participation metrics — conversations, messages, training."""
    session = ScopedSession()
    try:
        from ai.models.chat import Conversation, ChatMessage

        conversations = session.query(func.count(Conversation.id)).filter(
            Conversation.user_id == user_id, Conversation.is_deleted.is_(False)
        ).scalar() or 0

        messages = session.query(func.count(ChatMessage.id)).filter(
            ChatMessage.user_id == user_id, ChatMessage.is_deleted.is_(False)
        ).scalar() or 0

        trainings = session.query(TrainingAssignment).filter(
            TrainingAssignment.user_id == user_id,
            TrainingAssignment.is_deleted.is_(False),
        ).all()

        training_summary = {
            "total": len(trainings),
            "completed": sum(1 for t in trainings if t.status == TrainingStatusEnum.COMPLETED),
            "in_progress": sum(1 for t in trainings if t.status == TrainingStatusEnum.IN_PROGRESS),
            "assigned": sum(1 for t in trainings if t.status == TrainingStatusEnum.ASSIGNED),
        }

        return create_response("Activity retrieved", True, SUCCESS_CODE, data={
            "user_id": user_id,
            "conversations": conversations,
            "messages_sent": messages,
            "training": training_summary,
        })
    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        return create_response("Failed to retrieve activity", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /managers/:id/team/:userId/training
# ---------------------------------------------------------------------------

@manager_routes.post("/{manager_id}/team/{user_id}/training")
def assign_training(
    manager_id: str = Path(...),
    user_id: str = Path(...),
    title: str = "",
    description: Optional[str] = None,
    due_date: Optional[date] = None,
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """Assign a training module to a team member."""
    session = ScopedSession()
    try:
        if not title:
            return create_response("Title is required", False, VALIDATION_ERROR_CODE, status_code=400)

        assignment = TrainingAssignment(
            id=uuid.uuid4(),
            manager_id=manager_id,
            user_id=user_id,
            title=title,
            description=description,
            due_date=due_date,
            status=TrainingStatusEnum.ASSIGNED,
        )
        session.add(assignment)
        session.commit()

        return create_response("Training assigned", True, SUCCESS_CODE, data={
            "assignment_id": str(assignment.id),
            "user_id": user_id,
            "title": title,
            "status": "assigned",
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Error assigning training: {e}")
        return create_response("Failed to assign training", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /managers/:id/hiring
# ---------------------------------------------------------------------------

@manager_routes.get("/{manager_id}/hiring")
def get_hiring_pipeline(
    manager_id: str = Path(...),
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """Hiring pipeline — open positions, candidates, interviews."""
    session = ScopedSession()
    try:
        positions = (
            session.query(HiringPosition)
            .options(joinedload(HiringPosition.candidates))
            .filter(
                HiringPosition.manager_id == manager_id,
                HiringPosition.is_deleted.is_(False),
            )
            .all()
        )

        result = []
        for pos in positions:
            active_candidates = [c for c in pos.candidates if not c.is_deleted]
            result.append({
                "position_id": str(pos.id),
                "title": pos.title,
                "department": pos.department,
                "status": pos.status.value,
                "candidate_count": len(active_candidates),
                "candidates": [
                    {
                        "candidate_id": str(c.id),
                        "name": c.name,
                        "email": c.email,
                        "status": c.status.value,
                        "prism_score": c.prism_score,
                    }
                    for c in active_candidates
                ],
                "created_at": pos.created_at.isoformat() if pos.created_at else None,
            })

        return create_response("Hiring pipeline retrieved", True, SUCCESS_CODE, data={
            "positions": result,
            "total_positions": len(result),
        })
    except Exception as e:
        logger.error(f"Error getting hiring pipeline: {e}")
        return create_response("Failed to retrieve hiring pipeline", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /managers/:id/interviews
# ---------------------------------------------------------------------------

@manager_routes.get("/{manager_id}/interviews")
def get_interviews(
    manager_id: str = Path(...),
    date_filter: Optional[str] = Query(None, alias="date", description="ISO date, defaults to today"),
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """Today's interviews with candidate details."""
    session = ScopedSession()
    try:
        target_date = datetime.fromisoformat(date_filter).date() if date_filter else date.today()

        interviews = (
            session.query(Interview)
            .options(joinedload(Interview.candidate))
            .filter(
                Interview.interviewer_id == manager_id,
                cast(Interview.scheduled_at, Date) == target_date,
                Interview.is_deleted.is_(False),
            )
            .order_by(Interview.scheduled_at)
            .all()
        )

        result = []
        for iv in interviews:
            c = iv.candidate
            result.append({
                "interview_id": str(iv.id),
                "scheduled_at": iv.scheduled_at.isoformat(),
                "duration_minutes": iv.duration_minutes,
                "status": iv.status.value,
                "location": iv.location,
                "meeting_url": iv.meeting_url,
                "candidate": {
                    "candidate_id": str(c.id) if c else None,
                    "name": c.name if c else None,
                    "email": c.email if c else None,
                    "prism_score": c.prism_score if c else None,
                    "status": c.status.value if c else None,
                } if c else None,
            })

        return create_response("Interviews retrieved", True, SUCCESS_CODE, data={
            "interviews": result,
            "date": target_date.isoformat(),
            "count": len(result),
        })
    except Exception as e:
        logger.error(f"Error getting interviews: {e}")
        return create_response("Failed to retrieve interviews", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /managers/:id/team/invite
# ---------------------------------------------------------------------------

@manager_routes.post("/{manager_id}/team/invite")
def invite_team_member(
    manager_id: str = Path(...),
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    department: Optional[str] = None,
    position: Optional[str] = None,
    user_data: dict = Depends(require_role("manager", "super-admin")),
):
    """Invite a new user to the manager's team."""
    session = ScopedSession()
    try:
        if not email or not first_name:
            return create_response("Email and first_name required", False, VALIDATION_ERROR_CODE, status_code=400)

        # Check duplicate
        existing = session.query(Users).filter(Users.email == email).first()
        if existing:
            return create_response("User with this email already exists", False, VALIDATION_ERROR_CODE, status_code=400)

        # Get manager's org context
        mgr_profile = session.query(UserProfile).filter(UserProfile.user_id == manager_id).first()
        org_id = str(mgr_profile.org_id) if mgr_profile and mgr_profile.org_id else None

        return create_response("Invitation prepared", True, SUCCESS_CODE, data={
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "department": department,
            "position": position,
            "organization_id": org_id,
            "manager_id": manager_id,
            "next_step": "use_user_management_invite_endpoint",
        })
    except Exception as e:
        logger.error(f"Error inviting team member: {e}")
        return create_response("Failed to invite team member", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()
