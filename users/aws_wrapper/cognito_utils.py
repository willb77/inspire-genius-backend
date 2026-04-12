import os
import boto3
import hashlib
import base64
import hmac
import urllib.parse
import requests
import secrets
import string
import random
from botocore.exceptions import ClientError
from typing import Dict, Any, Optional

from prism_inspire.core.config import settings
from prism_inspire.core.log_config import logger

AWS_REGION = settings.AWS_REGION
AWS_SECRET_ACCESS_KEY = settings.AWS_SECRET_ACCESS_KEY
AWS_ACCESS_KEY_ID = settings.AWS_ACCESS_KEY_ID
USER_POOL_ID = settings.COGNITO_USER_POOL_ID
CLIENT_ID = settings.COGNITO_CLIENT_ID
CLIENT_SECRET = settings.COGNITO_CLIENT_SECRET

USER_NOT_FOUND = "User not found in Cognito"

# Log configuration information
if not CLIENT_ID or not USER_POOL_ID:
    logger.warning(
        "Missing Cognito configuration. "
        "Please set COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID "
        "environment variables."
    )

# Initialize Cognito Identity Provider client
cognito_client = boto3.client(
    'cognito-idp',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)


def get_secret_hash(username: str):
    """Calculate the secret hash for Cognito API calls

    Args:
        username: The username (email) of the user

    Returns:
        The secret hash string
    """
    if not CLIENT_SECRET:
        return None

    message = username + CLIENT_ID
    dig = hmac.new(
        key=bytes(CLIENT_SECRET, 'utf-8'),
        msg=bytes(message, 'utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def sign_up_user(
    password: str,
    email: str
) -> Dict[str, Any]:
    """
    Register a new user with AWS Cognito

    Args:
        password: User's password
        email: User's email (used as the username for Cognito)

    Returns:
        Dict containing status and message
    """
    try:
        # Prepare user attributes - include email, role, and is_onboarded
        user_attributes = [
            {'Name': 'email', 'Value': email},
            {'Name': 'custom:role', 'Value': 'user'},
            {'Name': 'custom:is_onboarded', 'Value': 'false'}
        ]

        # Use email as the username for Cognito
        username = email

        # Prepare signup parameters
        signup_params = {
            'ClientId': CLIENT_ID,
            'Username': username,
            'Password': password,
            'UserAttributes': user_attributes
        }

        # Add SECRET_HASH if client secret is configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            signup_params['SecretHash'] = secret_hash

        # Sign up the user in Cognito
        response = cognito_client.sign_up(**signup_params)

        # Return success response
        return {
            'status': True,
            'message': 'User registration successful. '
                       'Please check your email for verification code.',
            'user_id': response['UserSub']
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get(
            'Message', str(e)
        )

        logger.error(f"Cognito error: {error_code} - {error_message}")

        # Handle specific error cases
        if error_code == 'UsernameExistsException':
            return {
                'status': False,
                'message': 'Email address already exists. Please use '
                           'a different email address.'
            }
        elif error_code == 'InvalidPasswordException':
            return {
                'status': False,
                'message': 'Password does not meet requirements. '
                           'Please use a stronger password.'
            }
        elif error_code == 'InvalidParameterException':
            return {
                'status': False,
                'message': f'Invalid parameters provided. '
                           f'{error_message}'
            }
        else:
            return {
                'status': False,
                'message': f'Registration failed: {error_message}'
            }
    except Exception as e:
        logger.error(f"Unexpected error during signup: {str(e)}")
        return {
            'status': False,
            'message': 'An unexpected error occurred during '
                       'registration.'
        }


def delete_cognito_user(username: str) -> Dict[str, Any]:
    """
    Delete a user from AWS Cognito (admin operation)

    Args:
        username: User's email address

    Returns:
        Dict containing status and message
    """
    try:
        # Prepare delete parameters
        delete_params = {
            'UserPoolId': USER_POOL_ID,
            'Username': username
        }

        # Delete the user from Cognito
        cognito_client.admin_delete_user(**delete_params)

        logger.info(f"Successfully deleted user from Cognito: {username}")
        return {
            'status': True,
            'message': 'User deleted from Cognito successfully'
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(
            f"Cognito error during user deletion:{error_code}-{error_message}"
        )

        if error_code == 'UserNotFoundException':
            # User doesn't exist in Cognito, which is fine for our rollback
            return {
                'status': True,
                "message": USER_NOT_FOUND + " (already deleted or never existed)"
            }
        else:
            return {
                'status': False,
                'message': (
                    f'Failed to delete user from Cognito: {error_message}'
                )
            }

    except Exception as e:
        logger.error(f"Unexpected error during user deletion: {str(e)}")
        return {
            'status': False,
            'message': 'An unexpected error occurred during user deletion'
        }


def confirm_signup(
    username: str, confirmation_code: str
) -> Dict[str, Any]:
    """
    Confirm user registration with verification code

    Args:
        username: User's email address
        confirmation_code: Verification code sent to user's email

    Returns:
        Dict containing status and message
    """
    try:
        # Prepare confirmation parameters
        confirm_params = {
            'ClientId': CLIENT_ID,
            'Username': username,
            'ConfirmationCode': confirmation_code
        }

        # Add SECRET_HASH if client secret is configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            confirm_params['SecretHash'] = secret_hash

        # Confirm signup
        response = cognito_client.confirm_sign_up(**confirm_params)
        print(response)

        # Add user to the "user" group after successful verification
        group_result = add_user_to_cognito_group(username, "user")
        if not group_result['status']:
            logger.warning(
                f"User verified but failed to add to cognito group: "
                f"{group_result['message']}"
            )
        logger.info("User added to cognito group")

        return {
            'status': True,
            'message': 'User verification successful. You can now log in.'
        }
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get(
            'Message', str(e)
        )

        logger.error(
            f"Cognito error during confirmation: {error_code} - "
            f"{error_message}"
        )

        if error_code == 'CodeMismatchException':
            return {
                'status': False,
                'message': 'Invalid verification code. '
                           'Please try again.'
            }
        elif error_code == 'ExpiredCodeException':
            return {
                'status': False,
                'message': 'Verification code has expired. '
                           'Please request a new one.'
            }
        else:
            return {
                'status': False,
                'message': f'Verification failed: {error_message}'
            }
    except Exception as e:
        logger.error(f"Unexpected error during confirmation: {str(e)}")
        return {
            'status': False,
            'message': 'An unexpected error occurred during verification.'
        }


def verify_login(session, otp, username):
    try:
        challenge_responses = {
            'USERNAME': username,
            'EMAIL_OTP_CODE': otp
        }

        # Add SECRET_HASH inside ChallengeResponses if client
        # secret is configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            challenge_responses['SECRET_HASH'] = secret_hash

        response = cognito_client.respond_to_auth_challenge(
            ClientId=CLIENT_ID,
            ChallengeName='EMAIL_OTP',
            Session=session,
            ChallengeResponses=challenge_responses
        )

        auth_result = response.get('AuthenticationResult', {})
        access_token = auth_result.get('AccessToken')
        id_token = auth_result.get('IdToken')
        refresh_token = auth_result.get('RefreshToken')

        if access_token:
            return {
                'status': True,
                'message': 'Login successful',
                'access_token': access_token,
                'id_token': id_token,
                'refresh_token': refresh_token,
                'token_type': auth_result.get('TokenType')
            }
        else:
            return {
                'status': False,
                'message': 'Authentication failed - no tokens received'
            }

    except cognito_client.exceptions.CodeMismatchException:
        return {
            'status': False,
            'message': 'Invalid code'
        }
    except cognito_client.exceptions.ExpiredCodeException:
        return {
            'status': False,
            'message': 'Verification code expired'
        }
    except cognito_client.exceptions.NotAuthorizedException:
        return {
            'status': False,
            'message': 'Invalid session for the user, session is '
                       'expired.'
        }
    except Exception as e:
        return {
            'status': False,
            'message': str(e)
        }


def cognito_login(
        username: str, password: str
) -> Dict[str, Any]:
    """
    Authenticate a user with AWS Cognito

    Args:
        username: User's username
        password: User's password

    Returns:
        Dict containing status, message, and tokens if successful
    """
    try:
        # Prepare auth parameters
        auth_params = {
            'ClientId': CLIENT_ID,
            'AuthFlow': 'USER_PASSWORD_AUTH',
            'AuthParameters': {
                'USERNAME': username,
                'PASSWORD': password
            }
        }

        # Add SECRET_HASH if client secret is configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            auth_params['AuthParameters']['SECRET_HASH'] = secret_hash

        # Initiate auth
        response = cognito_client.initiate_auth(**auth_params)

        # Extract tokens
        if response.get("ChallengeName") == "EMAIL_OTP":
            return {
                'status': True,
                'session': response["Session"]
            }

        # Handle success without MFA
        if "AuthenticationResult" in response:
            return {
                'status': True,
                **response["AuthenticationResult"]
            }

        # Unexpected: neither MFA nor success
        logger.warning("Unexpected Cognito response: %s", response)
        return {
            'status': False,
            'message': 'Unexpected authentication response from Cognito'
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(f"Cognito login error: {error_code} - {error_message}")

        if error_code == 'NotAuthorizedException':
            return {
                'status': False,
                'message': 'Incorrect username or password'
            }
        elif error_code == 'UserNotConfirmedException':
            return {
                'status': False,
                'message': 'User is not confirmed. Please verify '
                           'your email first.'
            }
        elif error_code == 'UserNotFoundException':
            return {
                'status': False,
                'message': 'User does not exist'
            }
        else:
            return {
                'status': False,
                'message': f'Login failed: {error_message}'
            }
    except Exception as e:
        logger.error(f"Unexpected error during login: {str(e)}")
        return {
            'status': False,
            'message': 'An unexpected error occurred during login'
        }


def resend_confirmation_code(username: str) -> Dict[str, Any]:
    """
    Resend verification code to user's email address

    Args:
        username: User's username (email address)

    Returns:
        Dict containing status and message
    """
    try:
        # Prepare resend parameters
        resend_params = {
            'ClientId': CLIENT_ID,
            'Username': username
        }

        # Add SECRET_HASH if client secret is configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            resend_params['SecretHash'] = secret_hash

        # Resend confirmation code
        cognito_client.resend_confirmation_code(**resend_params)

        return {
            'status': True,
            'message': (
                'Verification code has been resent to your email address.'
            )
        }
    except ClientError as e:
        error_message = e.response.get('Error', {}).get(
            'Message', str(e)
        )
        logger.error(f"Cognito error during resend: {error_message}")

        return {
            'status': False,
            'message': f'Failed to resend verification code: '
                       f'{error_message}'
        }
    except Exception as e:
        logger.error(f"Unexpected error during resend: {str(e)}")
        return {
            'status': False,
            'message': 'An unexpected error occurred while resending '
                       'the code.'
        }


# OAuth Configuration
COGNITO_DOMAIN = settings.COGNITO_DOMAIN
# Use settings BASE_URL - should always be HTTPS in production
BASE_URL = settings.BASE_URL
REDIRECT_URI = f"{BASE_URL}/v1/social-auth/callback"

if COGNITO_DOMAIN and COGNITO_DOMAIN.startswith('https://'):
    COGNITO_DOMAIN = COGNITO_DOMAIN.replace('https://', '')
elif COGNITO_DOMAIN and COGNITO_DOMAIN.startswith('http://'):
    import logging
    logger = logging.getLogger(__name__)
    logger.error("HTTP protocol detected for COGNITO_DOMAIN. This is insecure and not allowed.")
    raise ValueError("COGNITO_DOMAIN must use HTTPS protocol for security. HTTP is not allowed.")

TOKEN_URL = f"https://{COGNITO_DOMAIN}/oauth2/token"


def generate_social_login_url(provider):
    """
    Generate OAuth login URL for social providers via Cognito

    Returns:
        Dict containing status, message, and login URL
    """
    try:
        # Use the same parameter order and format as Cognito UI
        # Match exactly what Cognito UI shows (only email and openid scopes)
        params = {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'scope': 'email openid',
            'redirect_uri': REDIRECT_URI,
            'identity_provider': provider
        }

        # Build URL with proper encoding
        cognito_login_url = (
            f"https://{COGNITO_DOMAIN}/oauth2/authorize?"
            f"{urllib.parse.urlencode(params)}"
        )

        logger.info(
            f"Generated login URL: {cognito_login_url}"
        )
        logger.info(f"COGNITO_DOMAIN: {COGNITO_DOMAIN}")
        logger.info(f"CLIENT_ID: {CLIENT_ID}")
        logger.info(f"REDIRECT_URI: {REDIRECT_URI}")

        return {
            'status': True,
            'message': 'login URL generated successfully',
            'login_url': cognito_login_url
        }

    except Exception as e:
        logger.exception(f"Error generating login URL: {e}")
        return {
            'status': False,
            'message': 'Failed to generate social login URL'
        }


def exchange_oauth_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Exchange OAuth authorization code for access tokens

    Args:
        code: Authorization code from Cognito OAuth callback

    Returns:
        Dict containing status, message, and tokens if successful
    """
    try:
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        }

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(TOKEN_URL, data=data, headers=headers)

        if response.status_code != 200:
            logger.error(
                f"Failed to exchange code for tokens: {response.text}"
            )
            return {
                'status': False,
                'message': 'Failed to exchange authorization code for tokens'
            }

        token_data = response.json()
        logger.info("Successfully exchanged OAuth code for tokens")
        return {
            'status': True,
            'message': 'Tokens retrieved successfully',
            **token_data
        }

    except Exception as e:
        logger.exception(f"Error exchanging OAuth code for tokens: {e}")
        return {
            'status': False,
            'message': 'Failed to exchange code for tokens'
        }


def extract_user_info_from_id_token(id_token: str) -> Dict[str, Any]:
    """
    Extract user information from Cognito ID token with proper JWT verification

    Args:
        id_token: JWT ID token from Cognito

    Returns:
        Dict containing status, message, and user info if successful
    """
    try:
        # Import the JWT verification function from auth module
        from users.auth import verify_jwt_token

        # Verify JWT signature and decode token securely
        decoded_token = verify_jwt_token(id_token)

        # Extract user information
        email = decoded_token.get('email')
        name = decoded_token.get('name')
        cognito_user_id = decoded_token.get('sub')

        # Determine auth provider from token
        identity_providers = decoded_token.get('identities', [])
        auth_provider = 'cognito'  # default

        if identity_providers:
            provider_name = identity_providers[0].get(
                'providerName', ''
            ).lower()
            if 'google' in provider_name:
                auth_provider = 'google'
            elif 'facebook' in provider_name:
                auth_provider = 'facebook'

        if not email or not cognito_user_id:
            logger.error("Missing required user information in ID token")
            return {
                'status': False,
                'message': 'Missing required user information in token'
            }

        # Extract first_name and last_name from full name if available
        first_name = None
        last_name = None
        if name:
            # Split full name into first and last
            name_parts = name.strip().split(' ', 1)
            first_name = name_parts[0] if len(name_parts) > 0 else None
            last_name = name_parts[1] if len(name_parts) > 1 else None

        logger.info(
            "Successfully extracted and verified user info for "
            f"{email} from {auth_provider}"
        )
        return {
            'status': True,
            'message': 'User information extracted successfully',
            'user_info': {
                'email': email,
                'name': name,
                'first_name': first_name,
                'last_name': last_name,
                'cognito_user_id': cognito_user_id,
                'auth_provider': auth_provider
            }
        }

    except Exception as e:
        logger.exception(f"Error extracting user info from ID token: {e}")
        return {
            'status': False,
            'message': 'Failed to extract user information from token'
        }


def add_user_to_cognito_group(
    username: str, group_name: str = None
) -> Dict[str, Any]:
    """
    Add a user to a Cognito user group

    Args:
        username: User's username (email address)
        group_name: Name of the group to add the user to.
                   If None, defaults to "{USER_POOL_ID}_user"

    Returns:
        Dict containing status and message
    """
    try:
        # Set default group name if not provided
        if group_name is None:
            group_name = "user"

        try:
            cognito_client.get_group(
                GroupName=group_name,
                UserPoolId=USER_POOL_ID
            )
        except cognito_client.exceptions.ResourceNotFoundException:
            cognito_client.create_group(
                GroupName=group_name,
                UserPoolId=USER_POOL_ID,
                Description="user group"
            )

        # Add user to the specified group
        cognito_client.admin_add_user_to_group(
            UserPoolId=USER_POOL_ID,
            Username=username,
            GroupName=group_name
        )

        logger.info(f"User {username} added to group {group_name}")
        return {
            'status': True,
            'message': f'User successfully added to {group_name} group'
        }
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(
            f"Cognito error adding user to group: "
            f"{error_code} - {error_message}"
        )
        return {
            'status': False,
            'message': f'Failed to add user to group: {error_message}'
        }
    except Exception as e:
        logger.error(f"Unexpected error adding user to group: {str(e)}")
        return {
            'status': False,
            'message': 'An error occurred while adding user to group'
        }


def get_cognito_username_by_user_id(user_id: str, fetch_name: bool = False):
    try:
        response = cognito_client.list_users(
            UserPoolId=USER_POOL_ID,
            Filter=f'sub = "{user_id}"',
            Limit=1
        )
        users = response.get("Users", [])
        if not users:
            return None

        user = users[0]
        username = user.get("Username")

        if not fetch_name:
            return username

        # Extract attributes into a dict
        attributes = {attr["Name"]: attr["Value"] for attr in user.get("Attributes", [])}

        full_name = attributes.get("name", "")
        first_name = ""
        last_name = ""

        if full_name:
            parts = full_name.strip().split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

        return {
            "username": username,
            "first_name": first_name,
            "last_name": last_name
        }

    except Exception as e:
        logger.error(f"Error retrieving Cognito username: {str(e)}")
        return None


class CognitoUserHandler:
    def __init__(self, client, user_pool_id: str, logger):
        self.client = client
        self.user_pool_id = user_pool_id
        self.logger = logger

    def update_user_attributes(
        self, username: str, attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            if not username:
                self.logger.warning("Cannot update Cognito: username is None/empty")
                return {"status": True, "message": "Skipped Cognito update (no username)"}

            is_active = attributes.pop("is_active", None)
            user_attributes = self._prepare_attributes(attributes)

            self._update_attributes(username, user_attributes)
            self._update_status(username, is_active)

            if not user_attributes and is_active is None:
                return {"status": True, "message": "No attributes to update"}

            return {"status": True, "message": "Cognito user updated successfully"}

        except ClientError as e:
            return self._handle_client_error(e)

        except Exception as e:
            self.logger.error(f"Unexpected error updating Cognito user {username}: {str(e)}")
            return {
                "status": False,
                "message": f"Unexpected error while updating Cognito user: {str(e)}",
            }

    # Helper methods
    def _prepare_attributes(self, attributes: Dict[str, Any]) -> list[Dict[str, str]]:
        return [
            {"Name": k, "Value": str(v)}
            for k, v in attributes.items()
            if v is not None
        ]

    def _update_attributes(self, username: str, user_attributes: list[Dict[str, str]]):
        if not user_attributes:
            return
        self.client.admin_update_user_attributes(
            UserPoolId=self.user_pool_id,
            Username=username,
            UserAttributes=user_attributes,
        )
        self.logger.info(f"Updated Cognito attributes for user: {username}")
        self.logger.debug(f"Updated attributes: {user_attributes}")

    def _update_status(self, username: str, is_active: Optional[bool]):
        if is_active is None:
            return
        if is_active:
            self.client.admin_enable_user(UserPoolId=self.user_pool_id, Username=username)
            self.logger.info(f"Enabled Cognito user: {username}")
        else:
            self.client.admin_disable_user(UserPoolId=self.user_pool_id, Username=username)
            self.logger.info(f"Disabled Cognito user: {username}")

    def _handle_client_error(self, e: ClientError) -> Dict[str, Any]:
        error = e.response.get("Error", {})
        code = error.get("Code", "Unknown")
        message = error.get("Message", str(e))

        self.logger.error(f"Cognito error updating user: {code} - {message}")

        if code == "UserNotFoundException":
            return {"status": False, "message": USER_NOT_FOUND}
        if code == "InvalidParameterException":
            return {"status": False, "message": f"Invalid parameters: {message}"}
        return {"status": False, "message": f"Failed to update Cognito user: {message}"}


def update_cognito_user_attributes(
    username: str, attributes: Dict[str, str]
) -> Dict[str, Any]:
    handler = CognitoUserHandler(cognito_client, USER_POOL_ID, logger)
    return handler.update_user_attributes(username, attributes)


def get_is_onboarded(user_sub: str) -> Optional[Dict[str, Optional[str]]]:
    try:
        username = get_cognito_username_by_user_id(user_sub)
        if not username:
            return None

        response = cognito_client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )

        is_onboarded = None
        email = None
        role = None

        for attr in response.get("UserAttributes", []):
            if attr["Name"] == "custom:is_onboarded":
                is_onboarded = attr["Value"]
            elif attr["Name"] == "email":
                email = attr["Value"]
            elif attr["Name"] == "custom:role":
                role = attr["Value"]

        return {
            "is_onboarded": is_onboarded,
            "email": email, 
            "role": role
        }

    except Exception as e:
        logger.error(f"Error fetching is_onboarded: {str(e)}")
    return None


def admin_create_user(
    email: str,
    temporary_password: str,
    user_attributes: Optional[Dict[str, str]] = None,
    role_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a user in Cognito using admin privileges with temporary password

    Args:
        email: User's email address (used as username)
        temporary_password: Temporary password for the user
        user_attributes: Additional user attributes
        role_name: Role name to store as custom attribute

    Returns:
        Dict containing status, message, and user details
    """
    try:
        # Prepare user attributes
        attributes = [
            {'Name': 'email', 'Value': email},
            {'Name': 'email_verified', 'Value': 'true'}  # Auto-verify email for invited users
        ]

        # Add role as custom attribute if provided
        if role_name:
            attributes.append({'Name': 'custom:role', 'Value': role_name})

        # Add additional attributes if provided
        if user_attributes:
            for name, value in user_attributes.items():
                attributes.append({'Name': name, 'Value': value})

        # Create user with admin privileges
        response = cognito_client.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=attributes,
            TemporaryPassword=temporary_password,
            MessageAction='SUPPRESS',  # Don't send welcome email, we'll send custom invitation
            ForceAliasCreation=False
        )

        logger.info(f"Successfully created user in Cognito: {email} with role: {role_name}")

        # Extract user_id (sub) from attributes
        user_id = None
        for attr in response['User']['Attributes']:
            if attr['Name'] == 'sub':
                user_id = attr['Value']
                break

        return {
            'status': True,
            'message': 'User created successfully in Cognito',
            'user_id': user_id,
            'username': response['User']['Username'],
            'user_status': response['User']['UserStatus']
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(f"Cognito admin_create_user error: {error_code} - {error_message}")

        return {
            'status': False,
            'message': error_message,
            'error_code': error_code
        }

    except Exception as e:
        logger.error(f"Unexpected error creating user in Cognito: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to create user in Cognito: {str(e)}'
        }


def admin_respond_to_auth_challenge(
    username: str,
    challenge_name: str,
    challenge_responses: Dict[str, str],
    session: Optional[str] = None
) -> Dict[str, Any]:
    """
    Respond to authentication challenge using admin privileges

    Args:
        username: User's username (email)
        challenge_name: Name of the challenge (e.g., 'NEW_PASSWORD_REQUIRED')
        challenge_responses: Challenge response parameters
        session: Session token from previous auth attempt

    Returns:
        Dict containing status, message, and auth result
    """
    try:
        # Prepare challenge response parameters
        params = {
            'UserPoolId': USER_POOL_ID,
            'ClientId': CLIENT_ID,
            'ChallengeName': challenge_name,
            'ChallengeResponses': challenge_responses
        }

        # Add session if provided
        if session:
            params['Session'] = session

        # Add secret hash if configured
        secret_hash = get_secret_hash(username)
        if secret_hash:
            params['ChallengeResponses']['SECRET_HASH'] = secret_hash

        # Respond to challenge
        response = cognito_client.admin_respond_to_auth_challenge(**params)

        logger.info(f"Successfully responded to auth challenge for user: {username}")

        return {
            'status': True,
            'message': 'Challenge response successful',
            'challenge_name': response.get('ChallengeName'),
            'session': response.get('Session'),
            'authentication_result': response.get('AuthenticationResult')
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(f"Cognito admin_respond_to_auth_challenge error: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to respond to auth challenge: {error_message}',
            'error_code': error_code
        }

    except Exception as e:
        logger.error(f"Unexpected error responding to auth challenge: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to respond to auth challenge: {str(e)}'
        }


def generate_temporary_password(length: int = 12) -> str:
    """
    Generate a secure temporary password for user invitations

    Args:
        length: Length of the password (default: 12)

    Returns:
        Secure temporary password string
    """
    # Define character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special_chars = "!@#$%^&*"

    # Ensure password has at least one character from each set
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special_chars)
    ]

    # Fill the rest with random characters from all sets
    all_chars = lowercase + uppercase + digits + special_chars
    for _ in range(length - 4):
        password.append(secrets.choice(all_chars))

    # Shuffle the password list using cryptographically secure Fisher-Yates shuffle
    for i in range(len(password) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        password[i], password[j] = password[j], password[i]
    return ''.join(password)


def admin_set_user_password(
    username: str,
    password: str,
    permanent: bool = True
) -> Dict[str, Any]:
    """
    Set user password using admin privileges (for invitation acceptance)

    Args:
        username: User's username (email)
        password: New password to set
        permanent: Whether the password is permanent (default: True)

    Returns:
        Dict containing status and message
    """
    try:
        # Set user password using admin privileges
        cognito_client.admin_set_user_password(
            UserPoolId=USER_POOL_ID,
            Username=username,
            Password=password,
            Permanent=permanent
        )

        logger.info(f"Successfully set password for user: {username}")

        return {
            'status': True,
            'message': 'Password set successfully'
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.error(f"Cognito admin_set_user_password error: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to set password: {error_message}',
            'error_code': error_code
        }

    except Exception as e:
        logger.error(f"Unexpected error setting user password: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to set password: {str(e)}'
        }


def get_cognito_user_status(username: str) -> Dict[str, Any]:
    """
    Get comprehensive user status from Cognito user pool

    Args:
        username: User's username (email)

    Returns:
        Dict containing user status information
    """
    try:
        response = cognito_client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username
        )

        # Extract user attributes
        attributes = {}
        for attr in response.get('UserAttributes', []):
            attributes[attr['Name']] = attr['Value']

        return {
            'status': True,
            'user_status': response.get('UserStatus'),
            'enabled': response.get('Enabled', False),
            'email': attributes.get('email'),
            'email_verified': attributes.get('email_verified') == 'true',
            'user_create_date': response.get('UserCreateDate'),
            'user_last_modified_date': response.get('UserLastModifiedDate'),
            'attributes': attributes,
            'mfa_options': response.get('MFAOptions', [])
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        if error_code == 'UserNotFoundException':
            return {
                'status': False,
                'user_exists': False,
                'message': USER_NOT_FOUND,
                'error_code': error_code
            }

        logger.error(f"Error getting Cognito user status: {error_code} - {error_message}")

        return {
            'status': False,
            'message': f'Failed to get user status: {error_message}',
            'error_code': error_code
        }

    except Exception as e:
        logger.error(f"Unexpected error getting user status: {str(e)}")

        return {
            'status': False,
            'message': f'Failed to get user status: {str(e)}'
        }


def verify_user_account_activation(username: str) -> Dict[str, Any]:
    """
    Comprehensive verification that user account is properly activated

    Args:
        username: User's username (email)

    Returns:
        Dict containing activation verification results
    """
    try:
        # Get user status from Cognito
        user_status = get_cognito_user_status(username)

        if not user_status.get('status'):
            return {
                'status': False,
                'activated': False,
                'message': USER_NOT_FOUND,
                'checks': {
                    'cognito_user_exists': False,
                    'user_status_confirmed': False,
                    'email_verified': False,
                    'account_enabled': False
                }
            }

        # Perform comprehensive checks
        checks = {
            'cognito_user_exists': True,
            'user_status_confirmed': user_status.get('user_status') == 'CONFIRMED',
            'email_verified': user_status.get('email_verified', False),
            'account_enabled': user_status.get('enabled', False),
            'no_force_password_change': user_status.get('user_status') != 'FORCE_CHANGE_PASSWORD'
        }

        # Determine if account is fully activated
        all_checks_passed = all(checks.values())

        return {
            'status': True,
            'activated': all_checks_passed,
            'user_status': user_status.get('user_status'),
            'email': user_status.get('email'),
            'checks': checks,
            'message': 'Account fully activated' if all_checks_passed else 'Account activation incomplete',
            'user_details': user_status
        }

    except Exception as e:
        logger.error(f"Error verifying user account activation: {str(e)}")

        return {
            'status': False,
            'activated': False,
            'message': f'Failed to verify account activation: {str(e)}',
            'checks': {
                'cognito_user_exists': False,
                'user_status_confirmed': False,
                'email_verified': False,
                'account_enabled': False
            }
        }
