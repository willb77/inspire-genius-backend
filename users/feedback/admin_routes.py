from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from typing import Optional

from sqlalchemy import func, extract

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role, log_access
from users.models.feedback import Feedback, FeedbackCorrection, AgentMemory
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    VALIDATION_ERROR_CODE,
)

feedback_admin_routes = APIRouter(prefix="/admin/feedback", tags=["Feedback Admin"])


@feedback_admin_routes.get("/stats")
def get_feedback_stats(
    user_data: dict = Depends(require_role("super-admin")),
):
    """Aggregate feedback statistics."""
    session = ScopedSession()
    try:
        log_access(user_data, "feedback_admin", action="stats")

        base = session.query(Feedback).filter(Feedback.is_deleted.is_(False))

        total_feedback = base.count()
        thumbs_up_count = base.filter(Feedback.feedback_type == "thumbs_up").count()
        thumbs_down_count = base.filter(Feedback.feedback_type == "thumbs_down").count()
        correction_count = base.filter(Feedback.feedback_type == "correction").count()

        thumbs_total = thumbs_up_count + thumbs_down_count
        thumbs_up_ratio = round(thumbs_up_count / thumbs_total, 4) if thumbs_total > 0 else 0.0

        # Top agents
        agent_rows = (
            base.with_entities(
                Feedback.agent_id,
                func.count(Feedback.id).label("count"),
            )
            .filter(Feedback.agent_id.isnot(None))
            .group_by(Feedback.agent_id)
            .order_by(func.count(Feedback.id).desc())
            .limit(10)
            .all()
        )
        top_agents = [
            {"agent_id": str(row.agent_id), "count": row.count}
            for row in agent_rows
        ]

        # Monthly trends
        trend_rows = (
            base.with_entities(
                extract("year", Feedback.created_at).label("yr"),
                extract("month", Feedback.created_at).label("mo"),
                func.count(Feedback.id).label("count"),
            )
            .group_by("yr", "mo")
            .order_by("yr", "mo")
            .all()
        )
        monthly_trends = [
            {
                "year": int(row.yr) if row.yr else None,
                "month": int(row.mo) if row.mo else None,
                "count": row.count,
            }
            for row in trend_rows
        ]

        return create_response(
            message="Feedback stats retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "total_feedback": total_feedback,
                "thumbs_up_count": thumbs_up_count,
                "thumbs_down_count": thumbs_down_count,
                "correction_count": correction_count,
                "thumbs_up_ratio": thumbs_up_ratio,
                "top_agents": top_agents,
                "monthly_trends": monthly_trends,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching feedback stats: {str(e)}")
        return create_response(
            message="Failed to retrieve feedback stats",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_admin_routes.get("/corrections")
def list_corrections(
    status: Optional[str] = Query("pending", description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role("super-admin")),
):
    """Correction review queue with feedback info."""
    session = ScopedSession()
    try:
        log_access(user_data, "feedback_admin", action="list_corrections")

        query = session.query(FeedbackCorrection)
        if status:
            query = query.filter(FeedbackCorrection.status == status)

        total = query.count()
        offset = (page - 1) * limit
        records = query.order_by(FeedbackCorrection.created_at.desc()).offset(offset).limit(limit).all()

        items = []
        for c in records:
            fb = c.feedback
            items.append({
                "id": str(c.id),
                "feedback_id": str(c.feedback_id),
                "original_response": c.original_response,
                "corrected_response": c.corrected_response,
                "status": c.status,
                "weight": c.weight,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
                "feedback_type": fb.feedback_type if fb else None,
                "agent_id": str(fb.agent_id) if fb and fb.agent_id else None,
                "user_id": str(fb.user_id) if fb else None,
            })

        return create_response(
            message="Corrections retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"items": items, "total": total, "page": page, "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error listing corrections: {str(e)}")
        return create_response(
            message="Failed to retrieve corrections",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_admin_routes.patch("/corrections/{correction_id}")
def review_correction(
    correction_id: str,
    action: str,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Approve or reject a correction. On approve, create AgentMemory (4.C4)."""
    if action not in ("approve", "reject"):
        return create_response(
            message="Action must be 'approve' or 'reject'",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    reviewer_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "feedback_admin", action=f"review_correction:{action}")

        correction = session.query(FeedbackCorrection).filter(
            FeedbackCorrection.id == correction_id
        ).first()

        if not correction:
            return create_response(
                message="Correction not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        now = datetime.now(timezone.utc)
        correction.status = "approved" if action == "approve" else "rejected"
        correction.reviewed_by = reviewer_id
        correction.reviewed_at = now

        memory_id = None
        if action == "approve":
            # 4.C4: Create agent memory from approved correction
            fb = correction.feedback
            agent_id = fb.agent_id if fb else None

            if agent_id:
                memory = AgentMemory(
                    agent_id=agent_id,
                    memory_type="correction",
                    content=correction.corrected_response,
                    source_id=correction.id,
                    weight=correction.weight,
                    is_active=True,
                )
                session.add(memory)
                session.flush()
                memory_id = str(memory.id)

        session.commit()

        data = {
            "correction_id": str(correction.id),
            "status": correction.status,
            "reviewed_at": correction.reviewed_at.isoformat() if correction.reviewed_at else None,
        }
        if memory_id:
            data["agent_memory_id"] = memory_id

        return create_response(
            message=f"Correction {correction.status} successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data=data,
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error reviewing correction: {str(e)}")
        return create_response(
            message="Failed to review correction",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@feedback_admin_routes.get("/export")
def export_feedback(
    format: str = Query("json", description="Export format: json or csv"),
    user_data: dict = Depends(require_role("super-admin")),
):
    """Export all feedback data as JSON or CSV."""
    if format not in ("json", "csv"):
        return create_response(
            message="Format must be 'json' or 'csv'",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    session = ScopedSession()
    try:
        log_access(user_data, "feedback_admin", action=f"export:{format}")

        records = (
            session.query(Feedback)
            .filter(Feedback.is_deleted.is_(False))
            .order_by(Feedback.created_at.desc())
            .all()
        )

        items = [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "response_id": r.response_id,
                "agent_id": str(r.agent_id) if r.agent_id else None,
                "feedback_type": r.feedback_type,
                "correction_text": r.correction_text,
                "rating": r.rating,
                "context_json": r.context_json,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        if format == "csv":
            if not items:
                csv_data = ""
            else:
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=items[0].keys())
                writer.writeheader()
                writer.writerows(items)
                csv_data = output.getvalue()
                output.close()

            return create_response(
                message="Feedback exported as CSV",
                status=True,
                error_code=SUCCESS_CODE,
                data={"format": "csv", "csv_data": csv_data, "total": len(items)},
            )

        return create_response(
            message="Feedback exported as JSON",
            status=True,
            error_code=SUCCESS_CODE,
            data={"format": "json", "items": items, "total": len(items)},
        )
    except Exception as e:
        logger.error(f"Error exporting feedback: {str(e)}")
        return create_response(
            message="Failed to export feedback",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
