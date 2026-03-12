import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import and_, or_, func, desc
from sqlalchemy.exc import IntegrityError
from prism_inspire.db.session import ScopedSession
from prism_inspire.core.log_config import logger
from prism_inspire.core.file_utils import S3FileHandler
from users.models.issue import Issue, IssueComment, IssueType, IssueStatusEnum, IssuePriorityEnum, IssueAttachment
from users.models.user import Users
from fastapi import UploadFile
from users.auth_service.utils import get_full_name


def create_issue(issue_data: Dict[str, Any], reported_by: str) -> Optional[str]:
    """
    Create a new issue
    
    Args:
        issue_data: Issue data dictionary
        reported_by: User ID reporting the issue
        
    Returns:
        Issue ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        issue_id = uuid.uuid4()
        
        issue = Issue(
            id=issue_id,
            subject=issue_data["subject"],
            description=issue_data["description"],
            priority=issue_data.get("priority", IssuePriorityEnum.MEDIUM.value),
            issue_type_id=issue_data.get("issue_type_id"),
            reported_by=reported_by,
            agent_id=issue_data.get("agent_id"),
            organization_id=issue_data.get("organization_id"),
            business_id=issue_data.get("business_id")
        )
        
        session.add(issue)
        session.commit()
        
        logger.info(f"Created issue {issue_id} by user {reported_by}")
        return str(issue_id)
        
    except IntegrityError as e:
        session.rollback()
        logger.error(f"Integrity error creating issue: {str(e)}")
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating issue: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_issue_by_id(issue_id: str, include_comments: bool = True) -> Optional[Issue]:
    """
    Get issue by ID

    Args:
        issue_id: Issue ID
        include_comments: Whether to include comments

    Returns:
        Issue object or None if not found
    """
    session = ScopedSession()
    try:
        from sqlalchemy.orm import joinedload

        query = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        )

        # Eager load relationships to avoid lazy loading issues
        query = query.options(
            joinedload(Issue.reporter),
            joinedload(Issue.issue_type),
            joinedload(Issue.organization),
            joinedload(Issue.business)
        )

        issue = query.first()

        if issue and include_comments:
            # Load comments
            comments = session.query(IssueComment).filter(
                and_(
                    IssueComment.issue_id == issue_id,
                    IssueComment.is_deleted == False
                )
            ).order_by(IssueComment.created_at.asc()).all()

            # Attach comments to issue (this would need proper relationship setup)
            issue._comments = comments

        return issue

    except Exception as e:
        logger.error(f"Error getting issue by ID: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_issues(
    reported_by: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    organization_id: Optional[str] = None,
    business_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    page: int = 1,
    limit: int = 10
) -> List[Issue]:
    """
    Get issues with filtering options

    Args:
        reported_by: Filter by reporter user ID
        status: Filter by issue status
        priority: Filter by issue priority
        organization_id: Filter by organization ID
        business_id: Filter by business ID
        agent_id: Filter by agent ID
        page: Page number for pagination
        limit: Number of items per page

    Returns:
        List of Issue objects
    """
    session = ScopedSession()
    try:
        query = session.query(Issue).filter(Issue.is_deleted == False)
        
        # Apply filters
        if reported_by:
            query = query.filter(Issue.reported_by == reported_by)

        if status:
            query = query.filter(Issue.status == status)
        
        if priority:
            query = query.filter(Issue.priority == priority)
        
        if organization_id:
            query = query.filter(Issue.organization_id == organization_id)
        
        if business_id:
            query = query.filter(Issue.business_id == business_id)
        
        if agent_id:
            query = query.filter(Issue.agent_id == agent_id)
        
        # Apply pagination
        offset = (page - 1) * limit
        issues = query.order_by(desc(Issue.created_at)).offset(offset).limit(limit).all()
        
        return issues
        
    except Exception as e:
        logger.error(f"Error getting issues: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def add_issue_comment(issue_id: str, comment_text: str, commented_by: str) -> Optional[str]:
    """
    Add a comment to an issue
    
    Args:
        issue_id: Issue ID
        comment_text: Comment text
        commented_by: User ID adding the comment
        
    Returns:
        Comment ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Verify issue exists
        issue = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        ).first()
        
        if not issue:
            logger.warning(f"Issue {issue_id} not found")
            return None
        
        comment_id = uuid.uuid4()
        comment = IssueComment(
            id=comment_id,
            issue_id=issue_id,
            comment=comment_text,
            commented_by=commented_by
        )
        
        session.add(comment)
        session.commit()
        
        logger.info(f"Added comment {comment_id} to issue {issue_id}")
        return str(comment_id)
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding issue comment: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_issue_comments(issue_id: str) -> List[IssueComment]:
    """
    Get comments for an issue
    
    Args:
        issue_id: Issue ID
        
    Returns:
        List of IssueComment objects
    """
    session = ScopedSession()
    try:
        comments = session.query(IssueComment).filter(
            and_(
                IssueComment.issue_id == issue_id,
                IssueComment.is_deleted == False
            )
        ).order_by(IssueComment.created_at.asc()).all()
        
        return comments
        
    except Exception as e:
        logger.error(f"Error getting issue comments: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_issues_for_user(
    user_id: str,
    role_info: dict,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    subject: Optional[str] = None
):
    session = ScopedSession()
    try:
        role = role_info.get("role_name", "").lower() if role_info else ""
        user_org_id = role_info.get("organization_id") if role_info else None

        query = session.query(Issue).filter(Issue.is_deleted == False)

        if role == "super-admin":
            # Super-admin sees all issues
            pass
        elif role == "admin":
            # Admin sees their own issues + issues from their organization (if they have one)
            if user_org_id:
                query = query.filter(
                    or_(
                        Issue.reported_by == user_id,
                        Issue.organization_id == user_org_id
                    )
                )
            else:
                # Admin without organization sees only their own issues
                query = query.filter(Issue.reported_by == user_id)
        else:
            # Regular users see only their own issues (with or without organization)
            query = query.filter(Issue.reported_by == user_id)

        # Apply filters
        if status:
            query = query.filter(Issue.status == status)

        if priority:
            query = query.filter(Issue.priority == priority)

        if subject:
            # Case-insensitive partial match for subject
            query = query.filter(Issue.subject.ilike(f"%{subject}%"))

        return query

    except Exception as e:
        logger.error(f"Error getting issues for user: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


# ============= Issue Type Management =============

def create_issue_type(name: str) -> Optional[str]:
    """
    Create a new issue type

    Args:
        name: Issue type name

    Returns:
        Issue type ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        issue_type_id = uuid.uuid4()

        issue_type = IssueType(
            id=issue_type_id,
            name=name
        )

        session.add(issue_type)
        session.commit()

        logger.info(f"Created issue type {issue_type_id}: {name}")
        return str(issue_type_id)

    except IntegrityError as e:
        session.rollback()
        logger.error(f"Issue type with name '{name}' already exists: {str(e)}")
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating issue type: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_all_issue_types(include_inactive: bool = False) -> List[IssueType]:
    """
    Get all issue types

    Args:
        include_inactive: Whether to include inactive types

    Returns:
        List of IssueType objects
    """
    session = ScopedSession()
    try:
        query = session.query(IssueType).filter(IssueType.is_deleted == False)

        if not include_inactive:
            query = query.filter(IssueType.is_active == True)

        issue_types = query.order_by(IssueType.name).all()
        return issue_types

    except Exception as e:
        logger.error(f"Error getting issue types: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_issue_type_by_id(issue_type_id: str) -> Optional[IssueType]:
    """
    Get issue type by ID

    Args:
        issue_type_id: Issue type ID

    Returns:
        IssueType object or None
    """
    session = ScopedSession()
    try:
        issue_type = session.query(IssueType).filter(
            and_(
                IssueType.id == issue_type_id,
                IssueType.is_deleted == False
            )
        ).first()

        return issue_type

    except Exception as e:
        logger.error(f"Error getting issue type by ID: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_issue_type_by_name(name: str) -> Optional[IssueType]:
    """
    Get issue type by name

    Args:
        name: Issue type name

    Returns:
        IssueType object or None
    """
    session = ScopedSession()
    try:
        issue_type = session.query(IssueType).filter(
            and_(
                IssueType.name == name,
                IssueType.is_deleted == False
            )
        ).first()

        return issue_type

    except Exception as e:
        logger.error(f"Error getting issue type by name: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


# ============= Admin Operations =============

def update_issue_status(issue_id: str, status: str, resolved_by: Optional[str] = None) -> bool:
    """
    Update issue status (admin operation)

    Args:
        issue_id: Issue ID
        status: New status
        resolved_by: User ID who resolved the issue

    Returns:
        True if successful, False otherwise
    """
    session = ScopedSession()
    try:
        issue = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        ).first()

        if not issue:
            logger.warning(f"Issue {issue_id} not found")
            return False

        issue.status = status

        if status in [IssueStatusEnum.RESOLVED.value, IssueStatusEnum.CLOSED.value]:
            issue.resolved_at = datetime.now()

        session.commit()
        logger.info(f"Updated issue {issue_id} status to {status}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating issue status: {str(e)}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def add_admin_comment(issue_id: str, comment_text: str, admin_user_id: str, change_status: Optional[str] = None) -> Optional[str]:
    """
    Add an admin comment to an issue

    Args:
        issue_id: Issue ID
        comment_text: Comment text
        admin_user_id: Admin user ID
        change_status: Optional status change

    Returns:
        Comment ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Verify issue exists
        issue = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        ).first()

        if not issue:
            logger.warning(f"Issue {issue_id} not found")
            return None

        # Add admin comment
        comment_id = uuid.uuid4()
        comment = IssueComment(
            id=comment_id,
            issue_id=issue_id,
            comment=comment_text,
            commented_by=admin_user_id,
            is_admin_comment=True
        )

        session.add(comment)

        # Update status if requested
        if change_status:
            issue.status = change_status
            if change_status in [IssueStatusEnum.RESOLVED.value, IssueStatusEnum.CLOSED.value]:
                issue.resolved_at = datetime.now()

        session.commit()

        logger.info(f"Admin comment {comment_id} added to issue {issue_id}")
        return str(comment_id)

    except Exception as e:
        session.rollback()
        logger.error(f"Error adding admin comment: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


# ============= Issue Attachments =============

def save_issue_attachment(
    issue_id: str,
    file: UploadFile,
    uploaded_by: str
) -> Optional[str]:
    """
    Save file attachment for an issue

    Args:
        issue_id: Issue ID
        file: Uploaded file
        uploaded_by: User ID who uploaded the file

    Returns:
        Attachment ID if successful, None otherwise
    """
    session = ScopedSession()
    try:
        # Verify issue exists
        issue = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        ).first()

        if not issue:
            logger.warning(f"Issue {issue_id} not found")
            return None

        # Upload file to S3
        file_handler = S3FileHandler(prefix="issue-attachments/")
        s3_key = file_handler.save_file(file, user_id=uploaded_by)

        if not s3_key:
            logger.error(f"Failed to upload file to S3 for issue {issue_id}")
            return None

        # Get file metadata
        file_extension = file.filename.split(".")[-1] if "." in file.filename else ""
        file_size = file.size if hasattr(file, 'size') else None

        # Create attachment record
        attachment_id = uuid.uuid4()
        attachment = IssueAttachment(
            id=attachment_id,
            issue_id=issue_id,
            filename=file.filename,
            original_filename=file.filename,
            file_key=s3_key,
            file_type=file_extension,
            file_size=str(file_size) if file_size else None,
            content_type=file.content_type,
            uploaded_by=uploaded_by
        )

        session.add(attachment)
        session.commit()

        logger.info(f"Created attachment {attachment_id} for issue {issue_id}")
        return str(attachment_id)

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving issue attachment: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_issue_attachments(issue_id: str) -> List[IssueAttachment]:
    """
    Get all attachments for an issue

    Args:
        issue_id: Issue ID

    Returns:
        List of IssueAttachment objects
    """
    session = ScopedSession()
    try:
        attachments = session.query(IssueAttachment).filter(
            and_(
                IssueAttachment.issue_id == issue_id,
                IssueAttachment.is_deleted == False
            )
        ).order_by(IssueAttachment.created_at.asc()).all()

        return attachments

    except Exception as e:
        logger.error(f"Error getting issue attachments: {str(e)}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def generate_attachment_download_url(attachment: IssueAttachment, expiration: int = 3600) -> Optional[str]:
    """
    Generate presigned download URL for an attachment

    Args:
        attachment: IssueAttachment object
        expiration: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL string or None if failed
    """
    try:
        file_handler = S3FileHandler(prefix="issue-attachments/")
        download_url = file_handler.generate_presigned_url(
            attachment.file_key,
            expiration=expiration
        )
        return download_url
    except Exception as e:
        logger.error(f"Error generating download URL: {str(e)}")
        return None


def get_issue_data_for_email(issue_id: str) -> Optional[dict]:
    """
    Get issue data formatted for email notification.
    Extracts all data while session is active to avoid lazy loading issues.

    Args:
        issue_id: Issue ID

    Returns:
        Dict with issue data or None if not found
    """
    session = ScopedSession()
    try:
        from sqlalchemy.orm import joinedload

        # Query with eager loading
        issue = session.query(Issue).filter(
            and_(
                Issue.id == issue_id,
                Issue.is_deleted == False
            )
        ).options(
            joinedload(Issue.reporter),
            joinedload(Issue.issue_type),
            joinedload(Issue.organization),
            joinedload(Issue.business)
        ).first()

        if not issue:
            return None

        # Extract all data while session is active
        data = {
            "issue_id": str(issue.id),
            "subject": issue.subject,
            "priority": issue.priority,
            "reported_by_name": "Unknown User",
            "reported_by_email": "unknown@example.com",
            "issue_type_name": None,
            "organization_name": None
        }

        # Get reporter info
        if issue.reporter:
            data["reported_by_email"] = issue.reporter.email

            # Try to get user profile for name
            from users.models.user import UserProfile
            user_profile = session.query(UserProfile).filter(
                UserProfile.user_id == issue.reporter.user_id
            ).first()

            if user_profile:
                full_name = get_full_name(user_profile.first_name, user_profile.last_name)
                data["reported_by_name"] = full_name or issue.reporter.email
            else:
                data["reported_by_name"] = issue.reporter.email

        # Get issue type name
        if issue.issue_type:
            data["issue_type_name"] = issue.issue_type.name

        # Get organization name
        if issue.organization and hasattr(issue.organization, 'name'):
            data["organization_name"] = issue.organization.name

        return data

    except Exception as e:
        logger.error(f"Error getting issue data for email: {str(e)}")
        return None
    finally:
        session.close()
        ScopedSession.remove()
