import boto3
import json
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional, List
from prism_inspire.core.config import settings
from prism_inspire.core.log_config import logger


# Initialize SES client
ses_client = boto3.client(
    'ses',
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
)


def send_invitation_email(
    recipient_email: str,
    organization_name: str,
    role_name: str,
    invitation_token: str,
    user_name: str = None
) -> Dict[str, Any]:
    """
    Send invitation email using AWS SES with pre-configured InvitationTemplate

    This function sends template data to the 'InvitationTemplate' that must be
    manually created in AWS SES console. The template should include the following variables:

    Template Variables Expected:
    - {{user_name}}: Display name of the invited user
    - {{organization_name}}: Name of the organization user is being invited to
    - {{role_name}}: Role/position being assigned to the user
    - {{invitation_url}}: Complete URL for accepting the invitation

    Args:
        recipient_email: Email address of the invitee
        organization_name: Name of the organization
        role_name: Role being assigned
        invitation_token: Unique invitation token
        user_name: Name of the user being invited (optional, defaults to email prefix)

    Returns:
        Dict containing status, message, and message_id if successful

    Note:
        The 'InvitationTemplate' must be created manually in AWS SES with the
        template structure defined by the user. This function only provides
        the template data variables.
    """
    try:
        # Create invitation URL for the frontend
        invitation_url = f"{settings.FRONTEND_URL}/accept-invitation?token={invitation_token}"

        # Use provided name or extract from email as fallback
        display_name = user_name or recipient_email.split('@')[0].replace('.', ' ').title()

        # Template data variables for AWS SES InvitationTemplate
        # These variables must match the template created in AWS SES console
        template_data = {
            'user_name': display_name,
            'email': recipient_email,
            'organization_name': organization_name,
            'role_name': role_name,
            'invitation_url': invitation_url
        }

        # Send email using the pre-configured AWS SES template
        response = ses_client.send_templated_email(
            Source="Prism Support <alex-support@3pp.com>",
            Destination={
                'ToAddresses': [recipient_email]
            },
            Template='InvitationTemplate',  # Must exist in AWS SES
            TemplateData=json.dumps(template_data)
        )

        logger.info(f"Invitation email sent successfully to {recipient_email}. MessageId: {response['MessageId']}")

        return {
            'status': True,
            'message': 'Invitation email sent successfully',
            'message_id': response['MessageId'],
            'template_used': 'InvitationTemplate',
            'template_data': template_data
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        # Log specific SES errors for debugging
        if error_code == 'TemplateDoesNotExist':
            logger.error("SES Template 'InvitationTemplate' does not exist. Please create it in AWS SES console.")
        elif error_code == 'InvalidTemplate':
            logger.error("SES Template 'InvitationTemplate' is invalid. Check template variables.")

        logger.error(f"SES error sending invitation email: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to send invitation email: {error_message}',
            'error_code': error_code,
            'template_used': 'InvitationTemplate'
        }

    except Exception as e:
        logger.error(f"Unexpected error sending invitation email: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to send invitation email: {str(e)}'
        }


def send_password_reset_email(
    recipient_email: str,
    reset_token: str,
    user_name: str = None
) -> Dict[str, Any]:
    """
    Send password reset email using AWS SES template 'PasswordResetTemplate'
    
    Args:
        recipient_email: Email address of the user
        reset_token: Password reset token
        user_name: Name of the user
    
    Returns:
        Dict containing status and message
    """
    try:
        # Create reset URL
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

        # Use provided name or extract from email as fallback
        display_name = user_name or recipient_email.split('@')[0].replace('.', ' ').title()

        # Template data variables for AWS SES PasswordResetTemplate
        template_data = {
            'user_name': display_name,
            'reset_url': reset_url
        }

        # Send email using SES template
        response = ses_client.send_templated_email(
            Source="Prism Support <alex-support@3pp.com>",
            Destination={
                'ToAddresses': [recipient_email]
            },
            Template='PasswordResetTemplate',  # Must exist in AWS SES
            TemplateData=json.dumps(template_data)
        )

        logger.info(f"Password reset email sent successfully to {recipient_email}. MessageId: {response['MessageId']}")

        return {
            'status': True,
            'message': 'Password reset email sent successfully',
            'message_id': response['MessageId'],
            'template_used': 'PasswordResetTemplate',
            'template_data': template_data
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        # Log specific SES template errors
        if error_code == 'TemplateDoesNotExist':
            logger.error("SES Template 'PasswordResetTemplate' does not exist. Please create it in AWS SES console.")
        elif error_code == 'InvalidTemplate':
            logger.error("SES Template 'PasswordResetTemplate' is invalid. Check template variables.")

        logger.error(f"SES error sending password reset email: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to send password reset email: {error_message}',
            'error_code': error_code,
            'template_used': 'PasswordResetTemplate'
        }

    except Exception as e:
        logger.error(f"Unexpected error sending password reset email: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to send password reset email: {str(e)}'
        }


def send_new_issue_notification(
    recipient_emails: List[str],
    issue_id: str,
    subject: str,
    priority: str,
    reported_by_name: str,
    reported_by_email: str,
    issue_type: str = None,
    organization_name: str = None
) -> Dict[str, Any]:
    """
    Send new issue notification to super admins using AWS SES template 'NewIssueNotificationTemplate'

    Template Variables Expected:
    - {{issue_id}}: Issue ID
    - {{subject}}: Issue subject
    - {{priority}}: Issue priority (low, medium, high, critical)
    - {{reported_by_name}}: Name of user who reported the issue
    - {{reported_by_email}}: Email of user who reported the issue
    - {{issue_type}}: Type of issue (optional)
    - {{organization_name}}: Organization name (optional)
    - {{issue_url}}: URL to view the issue

    Args:
        recipient_emails: List of super admin email addresses
        issue_id: Issue ID
        subject: Issue subject
        priority: Issue priority
        reported_by_name: Name of user who reported the issue
        reported_by_email: Email of the reporter
        issue_type: Type of issue (optional)
        organization_name: Organization name (optional)

    Returns:
        Dict containing status, message, and details

    Note:
        The 'NewIssueNotificationTemplate' must be created manually in AWS SES console
    """
    if not recipient_emails:
        logger.warning("No recipient emails provided for new issue notification")
        return {
            'status': False,
            'message': 'No recipient emails provided'
        }

    try:
        # Create issue URL for the frontend
        issue_url = f"{settings.FRONTEND_URL}/issues/{issue_id}"

        # Template data variables for AWS SES NewIssueNotificationTemplate
        template_data = {
            'issue_id': issue_id,
            'subject': subject,
            'priority': priority.upper(),
            'reported_by_name': reported_by_name,
            'reported_by_email': reported_by_email,
            'issue_type': issue_type or "Not specified",
            'organization_name': organization_name or "Not specified",
            'issue_url': issue_url
        }

        # Send email to all recipients
        sent_count = 0
        failed_recipients = []

        for email in recipient_emails:
            try:
                response = ses_client.send_templated_email(
                    Source="Prism Support <alex-support@3pp.com>",
                    Destination={
                        'ToAddresses': [email]
                    },
                    Template='NewIssueNotificationTemplate',  # Must exist in AWS SES
                    TemplateData=json.dumps(template_data)
                )
                sent_count += 1
                logger.info(f"New issue notification sent to {email}. MessageId: {response['MessageId']}")
            except ClientError as e:
                failed_recipients.append(email)
                logger.error(f"Failed to send notification to {email}: {str(e)}")

        if sent_count > 0:
            return {
                'status': True,
                'message': f'Issue notification sent to {sent_count} super admin(s)',
                'sent_count': sent_count,
                'failed_count': len(failed_recipients),
                'failed_recipients': failed_recipients,
                'template_used': 'NewIssueNotificationTemplate',
                'template_data': template_data
            }
        else:
            return {
                'status': False,
                'message': 'Failed to send notification to any recipients',
                'failed_recipients': failed_recipients
            }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        # Log specific SES errors for debugging
        if error_code == 'TemplateDoesNotExist':
            logger.error("SES Template 'NewIssueNotificationTemplate' does not exist. Please create it in AWS SES console.")
        elif error_code == 'InvalidTemplate':
            logger.error("SES Template 'NewIssueNotificationTemplate' is invalid. Check template variables.")

        logger.error(f"SES error sending new issue notification: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to send new issue notification: {error_message}',
            'error_code': error_code,
            'template_used': 'NewIssueNotificationTemplate'
        }

    except Exception as e:
        logger.error(f"Unexpected error sending new issue notification: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to send new issue notification: {str(e)}'
        }
