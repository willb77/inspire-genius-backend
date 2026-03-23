from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_authenticated_user, log_access
from users.models.feedback import Feedback, FeedbackCorrection
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE,
    VALIDATION_ERROR_CODE,
)

feedback_routes = APIRouter(prefix="/feedback", tags=["Feedback"])

VALID_FEEDBACK_TYPES = {"thumbs_up", "thumbs_down", "correction", "suggestion"}


@feedback_routes.post("")
def create_feedback(
    feedback_type: str,
    response_id: str,
    agent_id: Optional[str] = None,
    correction_text: Optional[str] = None,
    rating: Optional[int] = None,
    context_json: Optional[str] = None,
    user_data: dict = Depends(require_authenticated_user()),
):
    """Create a new feedback record."""
    if feedback_type not in VALID_FEEDBACK_TYPES:
        return create_response(
            message=f"Invalid feedback_type. Must be one of: {', '.join(sorted(VALID_FEEDBACK_TYPES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    if rating is not None and (rating < 1 or rating > 5):
        return create_response(
            message="Rating must be between 1 and 5",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    user_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "feedback", action="create")

        fb = Feedback(
            user_id=user_id,
            response_id=response_id,
            agent_id=agent_id,
            feedback_type=feedback_type,
            correction_text=correction_text,
            rating=rating,
            context_json=context_json,
        )
        session.add(fb)
        session.flush()

        correction_record = None
        if feedback_type == "correction" and correction_text:
            correction_record = FeedbackCorrection(
                feedback_id=fb.id,
                original_response=response_id,
                corrected_response=correction_text,
                status="pending",
            )
            session.add(correction_record)

        session.commit()

        data = {
            "feedback_id": str(fb.id),
            "feedback_type": fb.feedback_type,
            "response_id": fb.response_id,
        }
        if correction_record:
            data["correction_id"] = str(correction_record.id)

        return create_response(
            message="Feedback submitted successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data=data,
            status_code=201,
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating feedback: {str(e)}")
        return create_response(
            message="Failed to submit feedback",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_routes.get("")
def list_feedback(
    feedback_type: Optional[str] = Query(None, description="Filter by feedback type"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_authenticated_user()),
):
    """List user's feedback history."""
    user_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "feedback", action="list")

        query = session.query(Feedback).filter(
            Feedback.user_id == user_id,
            Feedback.is_deleted.is_(False),
        )

        if feedback_type:
            query = query.filter(Feedback.feedback_type == feedback_type)

        total = query.count()
        offset = (page - 1) * limit
        records = query.order_by(Feedback.created_at.desc()).offset(offset).limit(limit).all()

        items = [
            {
                "id": str(r.id),
                "feedback_type": r.feedback_type,
                "response_id": r.response_id,
                "agent_id": str(r.agent_id) if r.agent_id else None,
                "rating": r.rating,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        return create_response(
            message="Feedback retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"items": items, "total": total, "page": page, "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error listing feedback: {str(e)}")
        return create_response(
            message="Failed to retrieve feedback",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_routes.get("/{feedback_id}")
def get_feedback(
    feedback_id: str,
    user_data: dict = Depends(require_authenticated_user()),
):
    """Get feedback detail. Verify ownership."""
    user_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "feedback", action="read")

        fb = session.query(Feedback).filter(
            Feedback.id == feedback_id,
            Feedback.is_deleted.is_(False),
        ).first()

        if not fb:
            return create_response(
                message="Feedback not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if str(fb.user_id) != str(user_id):
            return create_response(
                message="Access denied",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        corrections = []
        for c in (fb.corrections or []):
            corrections.append({
                "id": str(c.id),
                "original_response": c.original_response,
                "corrected_response": c.corrected_response,
                "status": c.status,
                "weight": c.weight,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            })

        data = {
            "id": str(fb.id),
            "feedback_type": fb.feedback_type,
            "response_id": fb.response_id,
            "agent_id": str(fb.agent_id) if fb.agent_id else None,
            "correction_text": fb.correction_text,
            "rating": fb.rating,
            "context_json": fb.context_json,
            "corrections": corrections,
            "created_at": fb.created_at.isoformat() if fb.created_at else None,
            "updated_at": fb.updated_at.isoformat() if fb.updated_at else None,
        }

        return create_response(
            message="Feedback retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data=data,
        )
    except Exception as e:
        logger.error(f"Error getting feedback: {str(e)}")
        return create_response(
            message="Failed to retrieve feedback",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_routes.delete("/{feedback_id}")
def delete_feedback(
    feedback_id: str,
    user_data: dict = Depends(require_authenticated_user()),
):
    """Soft delete feedback. Verify ownership."""
    user_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "feedback", action="delete")

        fb = session.query(Feedback).filter(
            Feedback.id == feedback_id,
            Feedback.is_deleted.is_(False),
        ).first()

        if not fb:
            return create_response(
                message="Feedback not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if str(fb.user_id) != str(user_id):
            return create_response(
                message="Access denied",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        fb.is_deleted = True
        session.commit()

        return create_response(
            message="Feedback deleted successfully",
            status=True,
            error_code=SUCCESS_CODE,
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting feedback: {str(e)}")
        return create_response(
            message="Failed to delete feedback",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
