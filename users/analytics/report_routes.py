from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.sql import func

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_authenticated_user, log_access
from users.models.analytics import AnalyticsReport as Report
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE,
)

report_routes = APIRouter(prefix="/reports", tags=["Reports"])

VALID_REPORT_TYPES = {"executive_summary", "team_performance", "cost_analysis"}
VALID_FORMATS = {"pdf", "csv"}
VALID_SCHEDULES = {"daily", "weekly", "monthly"}


# ── 5.C2-1  Generate a report ───────────────────────────────────────
@report_routes.post("/generate")
def generate_report(
    report_type: str = Query(..., description="executive_summary / team_performance / cost_analysis"),
    format: str = Query("pdf", description="pdf / csv"),
    title: Optional[str] = Query(None, description="Report title"),
    parameters_json: Optional[str] = Query(None, description="JSON generation params"),
    scheduled_cron: Optional[str] = Query(None, description="daily / weekly / monthly or null"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Create a report generation request."""
    if report_type not in VALID_REPORT_TYPES:
        return create_response(
            message=f"Invalid report_type '{report_type}'. Must be one of: {', '.join(sorted(VALID_REPORT_TYPES))}",
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

    if scheduled_cron and scheduled_cron not in VALID_SCHEDULES:
        return create_response(
            message=f"Invalid scheduled_cron '{scheduled_cron}'. Must be one of: {', '.join(sorted(VALID_SCHEDULES))}",
            status=False,
            error_code=VALIDATION_ERROR_CODE,
            status_code=400,
        )

    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "report_generate", action="create")

        report_id = uuid.uuid4()
        report_title = title or f"{report_type.replace('_', ' ').title()} Report"

        # Placeholder: immediately mark completed with a placeholder URL
        placeholder_url = f"https://reports.inspirex.ai/{report_id}.{format}"
        placeholder_key = f"reports/{user_id}/{report_id}.{format}"

        new_report = Report(
            id=report_id,
            user_id=user_id,
            report_type=report_type,
            title=report_title,
            status="completed",
            format=format,
            file_url=placeholder_url,
            file_key=placeholder_key,
            parameters_json=parameters_json,
            scheduled_cron=scheduled_cron,
            completed_at=func.now(),
        )
        session.add(new_report)
        session.commit()

        return create_response(
            message="Report generated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "report_id": str(report_id),
                "report_type": report_type,
                "title": report_title,
                "status": "completed",
                "format": format,
                "file_url": placeholder_url,
                "scheduled_cron": scheduled_cron,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error generating report: {str(e)}")
        return create_response(
            message="Failed to generate report",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C2-2  List reports ────────────────────────────────────────────
@report_routes.get("")
def list_reports(
    status: Optional[str] = Query(None, description="Filter by status"),
    report_type: Optional[str] = Query(None, description="Filter by report_type"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_authenticated_user()),
):
    """List the current user's reports with optional filters."""
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "report_list", action="read")

        query = session.query(Report).filter(
            Report.user_id == user_id,
            Report.is_deleted == False,
        )

        if status:
            query = query.filter(Report.status == status)
        if report_type:
            query = query.filter(Report.report_type == report_type)

        total = query.count()
        reports = (
            query.order_by(Report.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        report_list = [
            {
                "id": str(r.id),
                "report_type": r.report_type,
                "title": r.title,
                "status": r.status,
                "format": r.format,
                "file_url": r.file_url,
                "scheduled_cron": r.scheduled_cron,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in reports
        ]

        return create_response(
            message="Reports retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "reports": report_list,
                "total": total,
                "page": page,
                "limit": limit,
            },
        )
    except Exception as e:
        logger.error(f"Error listing reports: {str(e)}")
        return create_response(
            message="Failed to retrieve reports",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


# ── 5.C2-3  Download a report ───────────────────────────────────────
@report_routes.get("/{report_id}/download")
def download_report(
    report_id: str,
    format: Optional[str] = Query(None, description="Override format (pdf / csv)"),
    user_data: dict = Depends(require_authenticated_user()),
):
    """Return download URL / key for a report. Verifies ownership."""
    user_id = user_data.get("sub")

    session = ScopedSession()
    try:
        log_access(user_data, "report_download", action="read")

        report = (
            session.query(Report)
            .filter(
                Report.id == report_id,
                Report.is_deleted == False,
            )
            .first()
        )

        if not report:
            return create_response(
                message="Report not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if str(report.user_id) != str(user_id):
            return create_response(
                message="Access denied - you do not own this report",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=403,
            )

        if report.status != "completed":
            return create_response(
                message=f"Report is not ready for download (status: {report.status})",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
            )

        # Format override
        download_format = format if format in VALID_FORMATS else report.format
        if download_format == "csv":
            download_url = report.file_url.replace(".pdf", ".csv") if report.file_url else None
        else:
            download_url = report.file_url

        return create_response(
            message="Report download ready",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "report_id": str(report.id),
                "title": report.title,
                "format": download_format,
                "file_url": download_url,
                "file_key": report.file_key,
            },
        )
    except Exception as e:
        logger.error(f"Error downloading report: {str(e)}")
        return create_response(
            message="Failed to download report",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
