from fastapi import APIRouter, Depends, Path, Query, HTTPException, File, UploadFile, Form
from fastapi_utils.cbv import cbv
from typing import Optional, List
from uuid import UUID
from users.rbac.schema import get_user_role_info, get_super_admin_emails
from prism_inspire.core.file_utils import S3FileHandler
from users.aws_wrapper.ses_email_service import send_new_issue_notification
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND,
    FORBIDDEN_ERROR_CODE
)
from prism_inspire.core.log_config import logger
from users.decorators import require_authenticated_user
from users.auth_service.utils import get_full_name
from users.issues.req_resp_parser import (
    CreateIssueRequest,
    IssueCommentRequest,
    UpdateIssueStatusRequest,
    AdminCommentRequest
)
from users.issues.schema import (
    create_issue, get_issue_by_id,
    get_issues, add_issue_comment, get_issue_comments, get_issues_for_user,
    get_all_issue_types,
    update_issue_status, add_admin_comment,
    save_issue_attachment, get_issue_attachments, generate_attachment_download_url,
    get_issue_data_for_email
)
from users.models.issue import IssueStatusEnum, IssuePriorityEnum, Issue


issue_routes = APIRouter(prefix="/issues", tags=["Issue Reporting"])

went_wrong = "Something went wrong, please try again later"


# Authentication logic moved to users/decorators.py for centralization


class IssueHandler:
    def __init__(self, user_data: dict = Depends(require_authenticated_user())):
        self.user_id = user_data["sub"]
        self.role_info = self._get_user_role_info(self.user_id)

    # --- Shared helpers ---
    def _get_user_role_info(self, user_id: str) -> dict:
        info = get_user_role_info(user_id)
        info["role_name"] = info.get("role_name", "").lower()
        return info

    def _can_access_issue(self, issue) -> bool:
        role = self.role_info["role_name"]
        user_org_id = self.role_info.get("organization_id")

        if role == "super-admin":
            return True
        if role == "admin":
            return (
                str(issue.reported_by) == self.user_id or
                (issue.organization_id and str(issue.organization_id) == user_org_id)
            )
        return str(issue.reported_by) == self.user_id

    def _serialize_comment(self, comment) -> dict:
        return {
            "id": str(comment.id),
            "comment": comment.comment,
            "commented_by": str(comment.commented_by),
            "is_admin_comment": comment.is_admin_comment,
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
        }

    def _serialize_issue(self, issue, include_comments: bool = False, include_attachments: bool = False) -> dict:
        # Get reporter name from relationship
        reported_by_name = None
        if issue.reporter:
            if hasattr(issue.reporter, 'user_profile') and issue.reporter.user_profile:
                reported_by_name = get_full_name(
                    issue.reporter.user_profile.first_name,
                    issue.reporter.user_profile.last_name
                )
            if not reported_by_name:
                reported_by_name = issue.reporter.email

        # Get latest admin comment
        admin_comment = None
        comments = get_issue_comments(str(issue.id))
        admin_comments = [c for c in comments if c.is_admin_comment]
        if admin_comments:
            # Get the most recent admin comment
            latest_admin_comment = admin_comments[-1]
            admin_comment = {
                "id": str(latest_admin_comment.id),
                "comment": latest_admin_comment.comment,
                "commented_by": str(latest_admin_comment.commented_by),
                "created_at": latest_admin_comment.created_at.isoformat(),
            }

        data = {
            "id": str(issue.id),
            "subject": issue.subject,
            "description": issue.description,
            "status": issue.status,
            "priority": issue.priority,
            "issue_type_id": str(issue.issue_type_id) if issue.issue_type_id else None,
            "issue_type_name": issue.issue_type.name if issue.issue_type else None,
            "reported_by": str(issue.reported_by),
            "reported_by_name": reported_by_name,
            "agent_id": str(issue.agent_id) if issue.agent_id else None,
            "organization_id": str(issue.organization_id) if issue.organization_id else None,
            "business_id": str(issue.business_id) if issue.business_id else None,
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
            "is_open": issue.is_open,
            "is_resolved": issue.is_resolved,
            "age_in_days": issue.age_in_days,
            "admin_comment": admin_comment,
            "created_at": issue.created_at.isoformat(),
            "updated_at": issue.updated_at.isoformat(),
        }

        if include_comments:
            data["comments"] = [self._serialize_comment(c) for c in comments]

        if include_attachments:
            attachments = get_issue_attachments(str(issue.id))
            data["attachments"] = [
                {
                    "id": str(att.id),
                    "filename": att.original_filename,
                    "file_type": att.file_type,
                    "file_size": att.file_size,
                    "download_url": generate_attachment_download_url(att),
                    "uploaded_by": str(att.uploaded_by),
                    "created_at": att.created_at.isoformat()
                }
                for att in attachments
            ]

        return data

    def get_issue(self, issue_id: UUID):
        issue = get_issue_by_id(str(issue_id))
        if not issue:
            return create_response(
                message="Issue not found",
                error_code=NOT_FOUND,
                status=False,
                status_code=404
            )

        if not self._can_access_issue(issue):
            return create_response(
                message="Access denied",
                error_code=FORBIDDEN_ERROR_CODE,
                status=False,
                status_code=403
            )

        data = self._serialize_issue(issue, include_comments=True, include_attachments=True)
        return create_response(
            message="Issue retrieved successfully",
            error_code=SUCCESS_CODE,
            status=True,
            data=data
        )

    def list_issues(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        subject: Optional[str] = None
    ):
        # Apply filters based on role
        issues_query = get_issues_for_user(
            self.user_id,
            self.role_info,
            status=status,
            priority=priority,
            subject=subject
        )

        total = issues_query.count()
        issues = (
            issues_query
            .order_by(Issue.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        data = {
            "items": [self._serialize_issue(issue) for issue in issues],
            "page": page,
            "page_size": page_size,
            "total": total,
            "filters": {
                "status": status,
                "priority": priority,
                "subject": subject
            }
        }
        return create_response(
            message="Issues retrieved successfully",
            error_code=SUCCESS_CODE,
            status=True,
            data=data
        )


@cbv(issue_routes)
class IssueManagementView:
    
    @issue_routes.post("/", response_model=dict)
    def create_issue_endpoint(
        self,
        subject: str = Form(..., max_length=200, description="Issue subject"),
        description: str = Form(..., description="Issue description"),
        priority: str = Form("medium", description="Issue priority: low, medium, high, critical"),
        issue_type_id: Optional[str] = Form(None, description="Issue type UUID"),
        agent_id: Optional[str] = Form(None, description="Related agent UUID"),
        organization_id: Optional[str] = Form(None, description="Organization UUID"),
        business_id: Optional[str] = Form(None, description="Business UUID"),
        user_data: dict = Depends(require_authenticated_user()),
        attachments: Optional[List[UploadFile]] = File(default=None, description="Optional file attachments")
    ):
        """
        Create a new issue report with optional file attachments

        - **subject**: Issue subject (5-200 characters)
        - **description**: Detailed description (min 10 characters)
        - **priority**: Priority level (default: medium)
        - **issue_type_id**: Optional issue type UUID
        - **agent_id**: Optional related agent UUID
        - **organization_id**: Optional organization UUID
        - **business_id**: Optional business UUID
        - **attachments**: Optional file attachments (images, PDFs, etc.)
        """
        try:
            user_id = user_data["sub"]
            # Fetch user role info (can be None)
            user_role_info = get_user_role_info(user_id)
            logger.debug(f"user_role_info: {user_role_info}")

            # Validate priority
            try:
                priority_enum = IssuePriorityEnum(priority.lower())
            except ValueError:
                return create_response(
                    message=f"Invalid priority. Must be one of: {', '.join([p.value for p in IssuePriorityEnum])}",
                    error_code=VALIDATION_ERROR_CODE,
                    status=False,
                    status_code=400
                )

            # Resolve organization_id
            if organization_id:
                org_id = organization_id
            else:
                org_id = user_role_info.get("organization_id") if user_role_info else None

            # Resolve business_id
            if business_id:
                bus_id = business_id
            else:
                bus_id = user_role_info.get("business_id") if user_role_info else None

            # Helper function to validate UUID or return None
            def validate_uuid(value):
                if not value or value.strip() == "":
                    return None
                try:
                    # Validate it's a proper UUID
                    UUID(value)
                    return value
                except (ValueError, AttributeError):
                    return None

            # Prepare issue data
            issue_data = {
                "subject": subject,
                "description": description,
                "priority": priority_enum.value,
                "issue_type_id": validate_uuid(issue_type_id),
                "agent_id": validate_uuid(agent_id),
                "organization_id": validate_uuid(org_id),
                "business_id": validate_uuid(bus_id),
            }

            # Create issue
            issue_id = create_issue(issue_data, user_id)

            if not issue_id:
                return create_response(
                    message="Failed to create issue",
                    error_code=SOMETHING_WENT_WRONG,
                    status=False,
                    status_code=500
                )

            # Handle file attachments if provided
            uploaded_attachments = []
            failed_attachments = []

            # Process attachments if any were provided
            if attachments:
                # Filter out empty file inputs and process valid files
                valid_files = [f for f in attachments if f and f.filename]

                for file in valid_files:
                    attachment_id = save_issue_attachment(issue_id, file, user_id)
                    if attachment_id:
                        uploaded_attachments.append({
                            "id": attachment_id,
                            "filename": file.filename
                        })
                    else:
                        failed_attachments.append(file.filename)

            response_data = {
                "issue_id": issue_id,
                "attachments_uploaded": len(uploaded_attachments),
                "attachments_failed": len(failed_attachments)
            }

            if uploaded_attachments:
                response_data["uploaded_files"] = uploaded_attachments
            if failed_attachments:
                response_data["failed_files"] = failed_attachments

            # Send email notification to super admins
            try:
                super_admin_emails = get_super_admin_emails()
                if super_admin_emails:
                    # Get issue data for email (handles session management properly)
                    issue_data = get_issue_data_for_email(issue_id)
                    if issue_data:
                        # Send notification
                        email_result = send_new_issue_notification(
                            recipient_emails=super_admin_emails,
                            issue_id=issue_data["issue_id"],
                            subject=issue_data["subject"],
                            priority=issue_data["priority"],
                            reported_by_name=issue_data["reported_by_name"],
                            reported_by_email=issue_data["reported_by_email"],
                            issue_type=issue_data["issue_type_name"],
                            organization_name=issue_data["organization_name"]
                        )

                        logger.info(f"Email notification result: {email_result.get('message')}")
                        response_data["email_notification"] = email_result.get('status', False)
                    else:
                        logger.warning("Could not retrieve issue data for email notification")
                        response_data["email_notification"] = False
                else:
                    logger.warning("No super admin emails found for notification")
                    response_data["email_notification"] = False
            except Exception as email_error:
                logger.error(f"Failed to send email notification: {str(email_error)}")
                response_data["email_notification"] = False

            return create_response(
                message="Issue reported successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=response_data
            )

        except Exception as e:
            logger.error(f"Error creating issue: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @issue_routes.get("/", response_model=dict)
    def list_issues(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
        status: Optional[str] = Query(None, description="Filter by status (OPEN, IN_PROGRESS, RESOLVED, CLOSED)"),
        priority: Optional[str] = Query(None, description="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)"),
        subject: Optional[str] = Query(None, description="Filter by subject (partial match, case-insensitive)"),
        handler: IssueHandler = Depends()
    ):
        return handler.list_issues(
            page=page,
            page_size=page_size,
            status=status,
            priority=priority,
            subject=subject
        )

    # ============= Issue Type Endpoints =============

    @issue_routes.get("/types", response_model=dict)
    def list_issue_types(self):
        """Get all issue types (public endpoint for dropdown)"""
        try:
            issue_types = get_all_issue_types()

            data = [
                {
                    "id": str(it.id),
                    "name": it.name
                }
                for it in issue_types
            ]

            return create_response(
                message="Issue types retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data=data
            )

        except Exception as e:
            logger.error(f"Error listing issue types: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @issue_routes.get("/{issue_id}", response_model=dict)
    def get_issue(
        self,
        issue_id: UUID,
        handler: IssueHandler = Depends()
    ):
        return handler.get_issue(issue_id)


    @issue_routes.post("/{issue_id}/comments", response_model=dict)
    def add_comment(
        self,
        issue_id: UUID = Path(...),
        comment_request: IssueCommentRequest = ...,
        user_data: dict = Depends(require_authenticated_user())
    ):
        """Add a comment to an issue"""
        try:
            user_id = user_data["sub"]

            # Get existing issue to check access
            issue = get_issue_by_id(str(issue_id))

            if not issue:
                return create_response(
                    message="Issue not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            # Add comment
            comment_id = add_issue_comment(str(issue_id), comment_request.comment, user_id)

            if comment_id:
                return create_response(
                    message="Comment added successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"comment_id": comment_id}
                )

            return create_response(
                message="Failed to add comment",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        except Exception as e:
            logger.error(f"Error adding comment: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    # ============= Admin Endpoints =============

    @issue_routes.patch("/{issue_id}/status", response_model=dict)
    def update_issue_status_endpoint(
        self,
        issue_id: UUID,
        status_request: UpdateIssueStatusRequest,
        user_data: dict = Depends(require_authenticated_user())
    ):
        """Update issue status (admin only)"""
        try:
            user_id = user_data["sub"]
            role_info = get_user_role_info(user_id)
            role_name = role_info.get("role_name", "").lower()

            # Only admin and super-admin can update status
            if role_name not in ["admin", "super-admin"]:
                return create_response(
                    message="Only administrators can update issue status",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Check if issue exists
            issue = get_issue_by_id(str(issue_id))
            if not issue:
                return create_response(
                    message="Issue not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            success = update_issue_status(
                issue_id=str(issue_id),
                status=status_request.status.value,
                resolved_by=user_id
            )

            if success:
                return create_response(
                    message="Issue status updated successfully",
                    error_code=SUCCESS_CODE,
                    status=True
                )

            return create_response(
                message="Failed to update issue status",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        except Exception as e:
            logger.error(f"Error updating issue status: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

    @issue_routes.post("/{issue_id}/admin-comment", response_model=dict)
    def add_admin_comment_endpoint(
        self,
        issue_id: UUID,
        comment_request: AdminCommentRequest,
        user_data: dict = Depends(require_authenticated_user())
    ):
        """Add admin comment to an issue and optionally change status (admin only)"""
        try:
            user_id = user_data["sub"]
            role_info = get_user_role_info(user_id)
            role_name = role_info.get("role_name", "").lower()

            # Only admin and super-admin can add admin comments
            if role_name not in ["admin", "super-admin"]:
                return create_response(
                    message="Only administrators can add admin comments",
                    error_code=FORBIDDEN_ERROR_CODE,
                    status=False,
                    status_code=403
                )

            # Check if issue exists
            issue = get_issue_by_id(str(issue_id))
            if not issue:
                return create_response(
                    message="Issue not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            comment_id = add_admin_comment(
                issue_id=str(issue_id),
                comment_text=comment_request.comment,
                admin_user_id=user_id,
                change_status=comment_request.change_status.value if comment_request.change_status else None
            )

            if comment_id:
                return create_response(
                    message="Admin comment added successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"comment_id": comment_id}
                )

            return create_response(
                message="Failed to add admin comment",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        except Exception as e:
            logger.error(f"Error adding admin comment: {str(e)}")
            return create_response(
                error_code=SOMETHING_WENT_WRONG,
                message=went_wrong,
                status=False,
                status_code=500
            )

