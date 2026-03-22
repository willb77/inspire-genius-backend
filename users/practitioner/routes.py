import uuid
from decimal import Decimal
from typing import Optional
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, Body
from sqlalchemy import and_, or_, func as sa_func

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
from users.models.practitioner import (
    PractitionerClient,
    CoachingSession,
    CoachingSessionStatusEnum,
    PractitionerCredits,
    FollowUp,
)
from users.models.user import Users, UserProfile
from users.models.phase3 import CostRecord

practitioner_routes = APIRouter(prefix="/practitioner", tags=["Practitioner"])


# ---------------------------------------------------------------------------
# 1. GET /practitioner/clients — List clients
# ---------------------------------------------------------------------------
@practitioner_routes.get("/clients")
def list_clients(
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None, regex="^(active|inactive|pending)$"),
    sort: Optional[str] = Query("name", regex="^(name|date)$"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/clients", "list")
        practitioner_id = user_data.get("sub")

        query = (
            session.query(
                PractitionerClient,
                Users.email,
                UserProfile.first_name,
                UserProfile.last_name,
            )
            .join(Users, Users.user_id == PractitionerClient.client_id)
            .outerjoin(UserProfile, UserProfile.user_id == PractitionerClient.client_id)
            .filter(
                PractitionerClient.practitioner_id == practitioner_id,
                PractitionerClient.is_deleted == False,
            )
        )

        # Filter by status
        if filter:
            query = query.filter(PractitionerClient.status == filter)

        # Search by name or email
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Users.email.ilike(search_term),
                    UserProfile.first_name.ilike(search_term),
                    UserProfile.last_name.ilike(search_term),
                )
            )

        # Sorting
        if sort == "date":
            query = query.order_by(PractitionerClient.created_at.desc())
        else:
            query = query.order_by(
                sa_func.coalesce(UserProfile.first_name, Users.email).asc()
            )

        total = query.count()
        offset = (page - 1) * limit
        results = query.offset(offset).limit(limit).all()

        clients = []
        for pc, email, first_name, last_name in results:
            clients.append(
                {
                    "id": str(pc.id),
                    "client_id": str(pc.client_id),
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "prism_score": float(pc.prism_score) if pc.prism_score else None,
                    "session_count": pc.session_count,
                    "status": pc.status,
                    "notes": pc.notes,
                    "started_at": pc.started_at.isoformat() if pc.started_at else None,
                    "created_at": pc.created_at.isoformat() if pc.created_at else None,
                }
            )

        return create_response(
            message="Clients retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "clients": clients,
                "total": total,
                "page": page,
                "limit": limit,
            },
        )
    except Exception as e:
        logger.error(f"Error listing practitioner clients: {e}")
        return create_response(
            message="Failed to retrieve clients",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 2. GET /practitioner/clients/{client_id} — Client detail
# ---------------------------------------------------------------------------
@practitioner_routes.get("/clients/{client_id}")
def get_client_detail(
    client_id: str = Path(...),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, f"practitioner/clients/{client_id}", "read")
        practitioner_id = user_data.get("sub")

        pc = (
            session.query(PractitionerClient)
            .filter(
                PractitionerClient.practitioner_id == practitioner_id,
                PractitionerClient.client_id == client_id,
                PractitionerClient.is_deleted == False,
            )
            .first()
        )
        if not pc:
            return create_response(
                message="Client not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        # Client user info
        user = session.query(Users).filter(Users.user_id == client_id).first()
        profile = (
            session.query(UserProfile)
            .filter(UserProfile.user_id == client_id)
            .first()
        )

        client_info = {
            "client_id": str(pc.client_id),
            "email": user.email if user else None,
            "first_name": profile.first_name if profile else None,
            "last_name": profile.last_name if profile else None,
            "prism_score": float(pc.prism_score) if pc.prism_score else None,
            "session_count": pc.session_count,
            "status": pc.status,
            "notes": pc.notes,
            "started_at": pc.started_at.isoformat() if pc.started_at else None,
        }

        # Coaching history — last 10 sessions
        sessions_q = (
            session.query(CoachingSession)
            .filter(
                CoachingSession.practitioner_id == practitioner_id,
                CoachingSession.client_id == client_id,
                CoachingSession.is_deleted == False,
            )
            .order_by(CoachingSession.scheduled_at.desc())
            .limit(10)
            .all()
        )
        coaching_history = [
            {
                "id": str(s.id),
                "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                "duration_minutes": s.duration_minutes,
                "status": s.status.value if s.status else None,
                "session_type": s.session_type,
                "notes": s.notes,
                "summary": s.summary,
                "rating": s.rating,
                "credits_used": float(s.credits_used) if s.credits_used else None,
            }
            for s in sessions_q
        ]

        # Session notes (from PractitionerClient + recent session notes)
        session_notes = [
            {"source": "client_record", "notes": pc.notes},
        ]
        for s in sessions_q:
            if s.notes:
                session_notes.append(
                    {
                        "source": "session",
                        "session_id": str(s.id),
                        "date": s.scheduled_at.isoformat() if s.scheduled_at else None,
                        "notes": s.notes,
                    }
                )

        return create_response(
            message="Client detail retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "client": client_info,
                "coaching_history": coaching_history,
                "prism_profile": {},  # placeholder
                "session_notes": session_notes,
            },
        )
    except Exception as e:
        logger.error(f"Error getting client detail: {e}")
        return create_response(
            message="Failed to retrieve client detail",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 3. POST /practitioner/clients — Add client
# ---------------------------------------------------------------------------
@practitioner_routes.post("/clients")
def add_client(
    client_id: str = Body(..., embed=False),
    notes: Optional[str] = Body(None),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/clients", "create")
        practitioner_id = user_data.get("sub")

        # Body is JSON — re-parse for flexibility
        body = {"client_id": client_id, "notes": notes}
        client_id_val = body.get("client_id") or client_id
        notes_val = body.get("notes") or notes

        # Check duplicate
        existing = (
            session.query(PractitionerClient)
            .filter(
                PractitionerClient.practitioner_id == practitioner_id,
                PractitionerClient.client_id == client_id_val,
                PractitionerClient.is_deleted == False,
            )
            .first()
        )
        if existing:
            return create_response(
                message="Client already exists in your roster",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Verify user exists
        client_user = (
            session.query(Users).filter(Users.user_id == client_id_val).first()
        )
        if not client_user:
            return create_response(
                message="User not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        new_pc = PractitionerClient(
            id=uuid.uuid4(),
            practitioner_id=practitioner_id,
            client_id=client_id_val,
            notes=notes_val,
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        session.add(new_pc)
        session.commit()

        return create_response(
            message="Client added successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(new_pc.id),
                "client_id": str(new_pc.client_id),
                "status": new_pc.status,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding client: {e}")
        return create_response(
            message="Failed to add client",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 4. PATCH /practitioner/clients/{client_id} — Update client
# ---------------------------------------------------------------------------
@practitioner_routes.patch("/clients/{client_id}")
def update_client(
    client_id: str = Path(...),
    status: Optional[str] = Body(None),
    notes: Optional[str] = Body(None),
    prism_score: Optional[float] = Body(None),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, f"practitioner/clients/{client_id}", "update")
        practitioner_id = user_data.get("sub")

        pc = (
            session.query(PractitionerClient)
            .filter(
                PractitionerClient.practitioner_id == practitioner_id,
                PractitionerClient.client_id == client_id,
                PractitionerClient.is_deleted == False,
            )
            .first()
        )
        if not pc:
            return create_response(
                message="Client not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if status is not None:
            pc.status = status
        if notes is not None:
            pc.notes = notes
        if prism_score is not None:
            pc.prism_score = prism_score

        session.commit()

        return create_response(
            message="Client updated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "client_id": str(pc.client_id),
                "status": pc.status,
                "notes": pc.notes,
                "prism_score": float(pc.prism_score) if pc.prism_score else None,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating client: {e}")
        return create_response(
            message="Failed to update client",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 5. GET /practitioner/credits — Credit balance
# ---------------------------------------------------------------------------
@practitioner_routes.get("/credits")
def get_credits(
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/credits", "read")
        practitioner_id = user_data.get("sub")

        credits = (
            session.query(PractitionerCredits)
            .filter(PractitionerCredits.practitioner_id == practitioner_id)
            .first()
        )

        balance = {
            "total": float(credits.total_credits) if credits else 0,
            "used": float(credits.used_credits) if credits else 0,
            "reserved": float(credits.reserved_credits) if credits else 0,
            "available": float(credits.available_credits) if credits else 0,
        }

        # Usage history — last 10 sessions with credits_used
        usage_rows = (
            session.query(CoachingSession)
            .filter(
                CoachingSession.practitioner_id == practitioner_id,
                CoachingSession.credits_used > 0,
                CoachingSession.is_deleted == False,
            )
            .order_by(CoachingSession.created_at.desc())
            .limit(10)
            .all()
        )
        usage_history = [
            {
                "session_id": str(s.id),
                "client_id": str(s.client_id),
                "credits_used": float(s.credits_used) if s.credits_used else 0,
                "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                "status": s.status.value if s.status else None,
                "session_type": s.session_type,
            }
            for s in usage_rows
        ]

        return create_response(
            message="Credit balance retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "balance": balance,
                "usage_history": usage_history,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving credits: {e}")
        return create_response(
            message="Failed to retrieve credit balance",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 6. GET /practitioner/costs — Cost metrics
# ---------------------------------------------------------------------------
@practitioner_routes.get("/costs")
def get_costs(
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/costs", "read")
        practitioner_id = user_data.get("sub")

        # Cost records scoped to this user
        cost_rows = (
            session.query(CostRecord)
            .filter(CostRecord.user_id == practitioner_id)
            .order_by(CostRecord.created_at.desc())
            .all()
        )
        cost_records = [
            {
                "id": str(c.id),
                "category": c.category,
                "amount": float(c.amount) if c.amount else 0,
                "scope": c.scope,
                "description": c.description,
                "period_start": c.period_start.isoformat() if c.period_start else None,
                "period_end": c.period_end.isoformat() if c.period_end else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cost_rows
        ]

        # Credit info
        credits = (
            session.query(PractitionerCredits)
            .filter(PractitionerCredits.practitioner_id == practitioner_id)
            .first()
        )

        return create_response(
            message="Cost metrics retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "cost_records": cost_records,
                "credits_used": float(credits.used_credits) if credits else 0,
                "credits_remaining": float(credits.available_credits) if credits else 0,
                "revenue_summary": {},  # placeholder
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving cost metrics: {e}")
        return create_response(
            message="Failed to retrieve cost metrics",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 7. GET /practitioner/sessions — Session list
# ---------------------------------------------------------------------------
@practitioner_routes.get("/sessions")
def list_sessions(
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/sessions", "list")
        practitioner_id = user_data.get("sub")

        query = (
            session.query(
                CoachingSession,
                UserProfile.first_name,
                UserProfile.last_name,
            )
            .outerjoin(UserProfile, UserProfile.user_id == CoachingSession.client_id)
            .filter(
                CoachingSession.practitioner_id == practitioner_id,
                CoachingSession.is_deleted == False,
            )
        )

        if date:
            try:
                filter_date = datetime.strptime(date, "%Y-%m-%d").date()
                query = query.filter(
                    sa_func.date(CoachingSession.scheduled_at) == filter_date
                )
            except ValueError:
                return create_response(
                    message="Invalid date format. Use YYYY-MM-DD",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400,
                )

        if status:
            try:
                status_enum = CoachingSessionStatusEnum(status)
                query = query.filter(CoachingSession.status == status_enum)
            except ValueError:
                return create_response(
                    message=f"Invalid status value: {status}",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400,
                )

        query = query.order_by(CoachingSession.scheduled_at.desc())
        total = query.count()
        offset = (page - 1) * limit
        results = query.offset(offset).limit(limit).all()

        sessions_list = [
            {
                "id": str(s.id),
                "client_id": str(s.client_id),
                "client_name": f"{first or ''} {last or ''}".strip() or None,
                "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                "duration_minutes": s.duration_minutes,
                "status": s.status.value if s.status else None,
                "session_type": s.session_type,
                "notes": s.notes,
                "summary": s.summary,
                "rating": s.rating,
                "credits_used": float(s.credits_used) if s.credits_used else None,
            }
            for s, first, last in results
        ]

        return create_response(
            message="Sessions retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "sessions": sessions_list,
                "total": total,
                "page": page,
                "limit": limit,
            },
        )
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return create_response(
            message="Failed to retrieve sessions",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ---------------------------------------------------------------------------
# 8. POST /practitioner/sessions — Create session
# ---------------------------------------------------------------------------
@practitioner_routes.post("/sessions")
def create_session(
    client_id: str = Body(...),
    scheduled_at: str = Body(...),
    duration_minutes: int = Body(60),
    session_type: str = Body("one_on_one"),
    notes: Optional[str] = Body(None),
    user_data: dict = Depends(require_role_or_above("practitioner")),
):
    session = ScopedSession()
    try:
        log_access(user_data, "practitioner/sessions", "create")
        practitioner_id = user_data.get("sub")

        # Validate PractitionerClient relationship exists
        pc = (
            session.query(PractitionerClient)
            .filter(
                PractitionerClient.practitioner_id == practitioner_id,
                PractitionerClient.client_id == client_id,
                PractitionerClient.is_deleted == False,
            )
            .first()
        )
        if not pc:
            return create_response(
                message="Client not found in your roster. Add the client first.",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        # Parse scheduled_at
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_at)
        except (ValueError, TypeError):
            return create_response(
                message="Invalid scheduled_at format. Use ISO 8601.",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        new_session = CoachingSession(
            id=uuid.uuid4(),
            practitioner_client_id=pc.id,
            practitioner_id=practitioner_id,
            client_id=client_id,
            scheduled_at=scheduled_dt,
            duration_minutes=duration_minutes,
            status=CoachingSessionStatusEnum.SCHEDULED,
            session_type=session_type,
            notes=notes,
            credits_used=Decimal("1"),
        )
        session.add(new_session)
        session.commit()

        return create_response(
            message="Session created successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(new_session.id),
                "client_id": str(new_session.client_id),
                "scheduled_at": new_session.scheduled_at.isoformat(),
                "duration_minutes": new_session.duration_minutes,
                "status": new_session.status.value,
                "session_type": new_session.session_type,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating session: {e}")
        return create_response(
            message="Failed to create session",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
