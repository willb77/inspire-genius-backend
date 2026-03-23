from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.sql import func

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_authenticated_user, log_access, role_rank
from users.models.analytics import ExportJob
from users.models.phase3 import UserGoal, UserActivity
from users.models.user import UserProfile, Organization
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE,
)

export_routes = APIRouter(prefix="/analytics", tags=["Data Export"])

VALID_SCOPES = {"user", "team", "company", "platform"}
VALID_FORMATS = {"json", "csv"}

# Minimum role_rank required for each export scope
SCOPE_MIN_RANK = {
    "platform": 5,   # super-admin
    "company": 2,    # company-admin or above
    "team": 1,       # manager or above
    "user": 0,       # any authenticated user
}


def _check_export_scope_access(user_data: dict, scope: str) -> str | None:
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


def _build_export_data(session, scope: str, user_data: dict) -> tuple[list[dict], int]:
    """Query records based on scope and return (rows, total_count)."""
    user_id = user_data.get("sub")
    role_info = user_data.get("role_info", {})
    org_id = role_info.get("organization_id") if isinstance(role_info, dict) else None

    if scope == "user":
        goals = (
            session.query(UserGoal)
            .filter(UserGoal.user_id == user_id, UserGoal.is_deleted == False)
            .all()
        )
        activities = (
            session.query(UserActivity)
            .filter(UserActivity.user_id == user_id)
            .all()
        )
    elif scope == "team":
        # Manager's direct reports
        from users.models.user import EmployeeProfile
        manager_profile = (
            session.query(UserProfile.id)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        manager_profile_id = manager_profile.id if manager_profile else None
        if manager_profile_id:
            report_rows = (
                session.query(UserProfile.user_id)
                .join(EmployeeProfile, EmployeeProfile.user_profile_id == UserProfile.id)
                .filter(EmployeeProfile.manager_id == manager_profile_id)
                .all()
            )
            team_ids = [r.user_id for r in report_rows]
        else:
            team_ids = []

        goals = (
            session.query(UserGoal)
            .filter(UserGoal.user_id.in_(team_ids), UserGoal.is_deleted == False)
            .all()
        ) if team_ids else []
        activities = (
            session.query(UserActivity)
            .filter(UserActivity.user_id.in_(team_ids))
            .all()
        ) if team_ids else []
    elif scope == "company":
        org_user_rows = (
            session.query(UserProfile.user_id)
            .filter(UserProfile.org_id == org_id)
            .all()
        ) if org_id else []
        org_ids = [r.user_id for r in org_user_rows]

        goals = (
            session.query(UserGoal)
            .filter(UserGoal.user_id.in_(org_ids), UserGoal.is_deleted == False)
            .all()
        ) if org_ids else []
        activities = (
            session.query(UserActivity)
            .filter(UserActivity.user_id.in_(org_ids))
            .all()
        ) if org_ids else []
    else:  # platform
        goals = session.query(UserGoal).filter(UserGoal.is_deleted == False).all()
        activities = session.query(UserActivity).all()

    rows = []
    for g in goals:
        rows.append({
            "type": "goal",
            "id": str(g.id),
            "user_id": str(g.user_id),
            "title": g.title,
            "status": g.status,
            "progress_pct": g.progress_pct,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    for a in activities:
        rows.append({
            "type": "activity",
            "id": str(a.id),
            "user_id": str(a.user_id),
            "activity_type": a.activity_type,
            "description": a.description,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    return rows, len(rows)


def _serialize_csv(rows: list[dict]) -> str:
    """Convert list of dicts to CSV string."""
    if not rows:
        return ""
    output = io.StringIO()
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    fieldnames = sorted(all_keys)
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ── 5.C3-1  Start data export ───────────────────────────────────────
@export_routes.get("/export")
def start_export(
    scope: str = Query(..., description="user / team / company / platform"),
    format: str = Query(..., description="json / csv"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Bulk data export with scope-based RBAC. Returns job_id and inline data."""
    if scope not in VALID_SCOPES:
        return create_response(
            message=f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(VALID_SCOPES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    if format not in VALID_FORMATS:
        return create_response(
            message=f"Invalid format '{format}'. Must be one of: {', '.join(sorted(VALID_FORMATS))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    access_error = _check_export_scope_access(user_data, scope)
    if access_error:
        log_access(user_data, "analytics_export", action=f"denied:{scope}")
        return create_response(
            message=access_error,
            status=False,
            error_code=FORBIDDEN_ERROR_CODE,
            status_code=403,
        )

    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_export", action=f"create:{scope}")

        job_id = uuid.uuid4()

        # Build data inline
        rows, total_records = _build_export_data(session, scope, user_data)

        if format == "csv":
            result_data = _serialize_csv(rows)
        else:
            result_data = json.dumps(rows, default=str)

        # Create export job record
        job = ExportJob(
            id=job_id,
            user_id=user_id,
            scope=scope,
            format=format,
            status="completed",
            progress_pct=100,
            result_url=None,
            result_key=None,
            total_records=total_records,
            completed_at=func.now(),
        )
        session.add(job)
        session.commit()

        return create_response(
            message="Export completed successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "job_id": str(job_id),
                "scope": scope,
                "format": format,
                "status": "completed",
                "total_records": total_records,
                "data": rows if format == "json" else result_data,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error starting export: {str(e)}")
        return create_response(
            message="Failed to start export",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C3-2  Poll export job status ──────────────────────────────────
@export_routes.get("/export/{job_id}")
def get_export_status(
    job_id: str,
    user_data: dict = Depends(require_authenticated_user()),
):
    """Poll the status of an export job. Verifies ownership."""
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_export_status", action="read")

        job = session.query(ExportJob).filter(ExportJob.id == job_id).first()

        if not job:
            return create_response(
                message="Export job not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if str(job.user_id) != str(user_id):
            return create_response(
                message="Access denied - you do not own this export job",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        return create_response(
            message="Export job status retrieved",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "job_id": str(job.id),
                "scope": job.scope,
                "format": job.format,
                "status": job.status,
                "progress_pct": job.progress_pct,
                "total_records": job.total_records,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            },
        )
    except Exception as e:
        logger.error(f"Error fetching export status: {str(e)}")
        return create_response(
            message="Failed to retrieve export status",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C3-3  Download export result ──────────────────────────────────
@export_routes.get("/export/{job_id}/download")
def download_export(
    job_id: str,
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return the export result data. Verifies ownership and job completion."""
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "analytics_export_download", action="read")

        job = session.query(ExportJob).filter(ExportJob.id == job_id).first()

        if not job:
            return create_response(
                message="Export job not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if str(job.user_id) != str(user_id):
            return create_response(
                message="Access denied - you do not own this export job",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        if job.status != "completed":
            return create_response(
                message=f"Export is not ready for download (status: {job.status})",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Re-generate data for download (since we don't store inline in DB)
        rows, total_records = _build_export_data(session, job.scope, user_data)

        if job.format == "csv":
            result = _serialize_csv(rows)
        else:
            result = rows

        return create_response(
            message="Export download ready",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "job_id": str(job.id),
                "scope": job.scope,
                "format": job.format,
                "total_records": total_records,
                "data": result,
            },
        )
    except Exception as e:
        logger.error(f"Error downloading export: {str(e)}")
        return create_response(
            message="Failed to download export",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
