"""
Practitioner API endpoints (2.3)

All endpoints require the 'practitioner' role (or super-admin).
Prefix: /v1/practitioners
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, Path, Query, Body
from typing import Optional

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role
from users.response import (
    create_response, SUCCESS_CODE, SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE, NOT_FOUND,
)
from users.models.user import Users, UserProfile
from users.models.practitioner import (
    PractitionerClient, CoachingSession, SessionStatusEnum,
    PractitionerCredit, FollowUp, FollowUpStatusEnum, FollowUpPriorityEnum,
)
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, func, cast, Date

practitioner_routes = APIRouter(prefix="/practitioners", tags=["Practitioner"])


# ---------------------------------------------------------------------------
#  GET /practitioners/:id/clients
# ---------------------------------------------------------------------------

@practitioner_routes.get("/{practitioner_id}/clients")
def get_clients(
    practitioner_id: str = Path(...),
    status: Optional[str] = Query(None),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Client roster with PRISM scores and session counts."""
    session = ScopedSession()
    try:
        query = session.query(PractitionerClient).filter(
            PractitionerClient.practitioner_id == practitioner_id,
            PractitionerClient.is_deleted.is_(False),
        )
        if status:
            query = query.filter(PractitionerClient.status == status)

        clients = query.all()
        result = []
        for c in clients:
            client_user = session.query(Users).filter(Users.user_id == c.client_id).first()
            client_profile = session.query(UserProfile).filter(UserProfile.user_id == c.client_id).first()
            result.append({
                "client_relationship_id": str(c.id),
                "client_id": str(c.client_id),
                "email": client_user.email if client_user else None,
                "first_name": client_profile.first_name if client_profile else None,
                "last_name": client_profile.last_name if client_profile else None,
                "prism_score": c.prism_score,
                "session_count": c.session_count,
                "status": c.status,
                "started_at": c.started_at.isoformat() if c.started_at else None,
            })

        return create_response("Clients retrieved", True, SUCCESS_CODE, data={
            "clients": result,
            "total": len(result),
        })
    except Exception as e:
        logger.error(f"Error getting clients: {e}")
        return create_response("Failed to retrieve clients", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  POST /practitioners/:id/clients
# ---------------------------------------------------------------------------

@practitioner_routes.post("/{practitioner_id}/clients")
def add_client(
    practitioner_id: str = Path(...),
    client_id: str = Body(..., embed=True),
    notes: Optional[str] = Body(None, embed=True),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Add a client to the practitioner's roster."""
    session = ScopedSession()
    try:
        # Verify client exists
        client_user = session.query(Users).filter(Users.user_id == client_id).first()
        if not client_user:
            return create_response("Client user not found", False, NOT_FOUND, status_code=404)

        # Check duplicate
        existing = session.query(PractitionerClient).filter(
            PractitionerClient.practitioner_id == practitioner_id,
            PractitionerClient.client_id == client_id,
            PractitionerClient.is_deleted.is_(False),
        ).first()
        if existing:
            return create_response("Client already in roster", False, VALIDATION_ERROR_CODE, status_code=400)

        pc = PractitionerClient(
            id=uuid.uuid4(),
            practitioner_id=practitioner_id,
            client_id=client_id,
            notes=notes,
        )
        session.add(pc)
        session.commit()

        return create_response("Client added", True, SUCCESS_CODE, data={
            "client_relationship_id": str(pc.id),
            "client_id": client_id,
        })
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding client: {e}")
        return create_response("Failed to add client", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /practitioners/:id/sessions
# ---------------------------------------------------------------------------

@practitioner_routes.get("/{practitioner_id}/sessions")
def get_sessions(
    practitioner_id: str = Path(...),
    date_filter: Optional[str] = Query(None, alias="date"),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Coaching sessions — today's + history."""
    session = ScopedSession()
    try:
        query = session.query(CoachingSession).filter(
            CoachingSession.practitioner_id == practitioner_id,
            CoachingSession.is_deleted.is_(False),
        )

        if date_filter:
            target = datetime.fromisoformat(date_filter).date()
            query = query.filter(cast(CoachingSession.scheduled_at, Date) == target)

        if status:
            try:
                status_enum = SessionStatusEnum(status)
                query = query.filter(CoachingSession.status == status_enum)
            except ValueError:
                pass

        total = query.count()
        offset = (page - 1) * limit
        sessions_list = query.order_by(CoachingSession.scheduled_at.desc()).offset(offset).limit(limit).all()

        result = []
        for s in sessions_list:
            client_user = session.query(Users).filter(Users.user_id == s.client_id).first()
            result.append({
                "session_id": str(s.id),
                "client_id": str(s.client_id),
                "client_email": client_user.email if client_user else None,
                "scheduled_at": s.scheduled_at.isoformat(),
                "duration_minutes": s.duration_minutes,
                "status": s.status.value,
                "session_type": s.session_type,
                "credits_used": float(s.credits_used) if s.credits_used else None,
                "rating": s.rating,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            })

        return create_response("Sessions retrieved", True, SUCCESS_CODE, data={
            "sessions": result,
            "pagination": {"total": total, "page": page, "limit": limit, "has_more": offset + limit < total},
        })
    except Exception as e:
        logger.error(f"Error getting sessions: {e}")
        return create_response("Failed to retrieve sessions", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /practitioners/:id/credits
# ---------------------------------------------------------------------------

@practitioner_routes.get("/{practitioner_id}/credits")
def get_credits(
    practitioner_id: str = Path(...),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Credit balance and usage."""
    session = ScopedSession()
    try:
        credit = session.query(PractitionerCredit).filter(
            PractitionerCredit.practitioner_id == practitioner_id
        ).first()

        if not credit:
            return create_response("Credits retrieved", True, SUCCESS_CODE, data={
                "practitioner_id": practitioner_id,
                "total_credits": 0,
                "used_credits": 0,
                "reserved_credits": 0,
                "available_credits": 0,
            })

        return create_response("Credits retrieved", True, SUCCESS_CODE, data={
            "practitioner_id": practitioner_id,
            "total_credits": float(credit.total_credits),
            "used_credits": float(credit.used_credits),
            "reserved_credits": float(credit.reserved_credits),
            "available_credits": float(credit.available_credits),
        })
    except Exception as e:
        logger.error(f"Error getting credits: {e}")
        return create_response("Failed to retrieve credits", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /practitioners/:id/followups
# ---------------------------------------------------------------------------

@practitioner_routes.get("/{practitioner_id}/followups")
def get_followups(
    practitioner_id: str = Path(...),
    status: Optional[str] = Query(None),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Follow-ups due with priority."""
    session = ScopedSession()
    try:
        query = session.query(FollowUp).filter(
            FollowUp.practitioner_id == practitioner_id,
            FollowUp.is_deleted.is_(False),
        )

        if status:
            try:
                status_enum = FollowUpStatusEnum(status)
                query = query.filter(FollowUp.status == status_enum)
            except ValueError:
                pass
        else:
            query = query.filter(FollowUp.status.in_([FollowUpStatusEnum.PENDING, FollowUpStatusEnum.OVERDUE]))

        followups = query.order_by(FollowUp.due_date).all()

        result = []
        for f in followups:
            client_user = session.query(Users).filter(Users.user_id == f.client_id).first()
            result.append({
                "followup_id": str(f.id),
                "client_id": str(f.client_id),
                "client_email": client_user.email if client_user else None,
                "title": f.title,
                "description": f.description,
                "due_date": f.due_date.isoformat() if f.due_date else None,
                "priority": f.priority.value,
                "status": f.status.value,
            })

        return create_response("Follow-ups retrieved", True, SUCCESS_CODE, data={
            "followups": result,
            "total": len(result),
        })
    except Exception as e:
        logger.error(f"Error getting follow-ups: {e}")
        return create_response("Failed to retrieve follow-ups", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
#  GET /practitioners/:id/dashboard
# ---------------------------------------------------------------------------

@practitioner_routes.get("/{practitioner_id}/dashboard")
def get_dashboard(
    practitioner_id: str = Path(...),
    user_data: dict = Depends(require_role("practitioner", "super-admin")),
):
    """Business KPIs — clients, satisfaction, utilization."""
    session = ScopedSession()
    try:
        active_clients = session.query(func.count(PractitionerClient.id)).filter(
            PractitionerClient.practitioner_id == practitioner_id,
            PractitionerClient.status == "active",
            PractitionerClient.is_deleted.is_(False),
        ).scalar() or 0

        total_sessions = session.query(func.count(CoachingSession.id)).filter(
            CoachingSession.practitioner_id == practitioner_id,
            CoachingSession.is_deleted.is_(False),
        ).scalar() or 0

        completed_sessions = session.query(func.count(CoachingSession.id)).filter(
            CoachingSession.practitioner_id == practitioner_id,
            CoachingSession.status == SessionStatusEnum.COMPLETED,
            CoachingSession.is_deleted.is_(False),
        ).scalar() or 0

        avg_rating = session.query(func.avg(CoachingSession.rating)).filter(
            CoachingSession.practitioner_id == practitioner_id,
            CoachingSession.rating.isnot(None),
            CoachingSession.is_deleted.is_(False),
        ).scalar()

        pending_followups = session.query(func.count(FollowUp.id)).filter(
            FollowUp.practitioner_id == practitioner_id,
            FollowUp.status.in_([FollowUpStatusEnum.PENDING, FollowUpStatusEnum.OVERDUE]),
            FollowUp.is_deleted.is_(False),
        ).scalar() or 0

        credit = session.query(PractitionerCredit).filter(
            PractitionerCredit.practitioner_id == practitioner_id
        ).first()

        return create_response("Dashboard retrieved", True, SUCCESS_CODE, data={
            "practitioner_id": practitioner_id,
            "active_clients": active_clients,
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "avg_satisfaction": round(float(avg_rating), 2) if avg_rating else None,
            "utilization_rate": round(completed_sessions / max(total_sessions, 1) * 100, 1),
            "pending_followups": pending_followups,
            "available_credits": float(credit.available_credits) if credit else 0,
        })
    except Exception as e:
        logger.error(f"Error getting dashboard: {e}")
        return create_response("Failed to retrieve dashboard", False, SOMETHING_WENT_WRONG, status_code=500)
    finally:
        session.close()
        ScopedSession.remove()
