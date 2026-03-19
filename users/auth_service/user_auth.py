import os
from urllib.parse import urlencode
from fastapi.exceptions import HTTPException
from fastapi import APIRouter, Query, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi_utils.cbv import cbv
from users.aws_wrapper.ses_email_service import send_password_reset_email
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    VALIDATION_ERROR_CODE,
    NOT_FOUND
)
from users.auth_service.schema import (
    create_user,
    update_user_password,
    update_user_verification_status,
    get_user_by_email
)
from users.auth_service.utils import check_password_hash
from .req_resp_parser import (
    LoginRequest,
    SignupRequest,
    RefreshTokenRequest,
    RequestPasswordResetRequest,
    ResetPasswordRequest,
    ChangePasswordRequest
)
from users.aws_wrapper.cognito_utils import (
    add_user_to_cognito_group,
    cognito_login,
    get_cognito_username_by_user_id,
    get_is_onboarded,
    resend_confirmation_code,
    sign_up_user,
    confirm_signup,
    verify_login,
    delete_cognito_user,
    generate_social_login_url,
    exchange_oauth_code_for_tokens,
    extract_user_info_from_id_token,
    admin_set_user_password,
    update_cognito_user_attributes
)

from users.auth import create_reset_token, refresh_token, verify_reset_token, verify_token
from prism_inspire.core.log_config import logger
from ai.agent_settings.schema import set_user_agent_preference
from ai.models.agents import Agent
from prism_inspire.db.session import ScopedSession



user_auth_route = APIRouter(
    prefix="",
    tags=["User Authentication"]
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://speech.pacewisdom.in")

@cbv(user_auth_route)
class SignupView:
    @user_auth_route.post("/signup")
    def post(self, signup_request: SignupRequest):
        try:
            # Check if user already exists
            existing_user = get_user_by_email(signup_request.email)
            if existing_user:
                # If user exists but email is not verified, allow resend of verification
                if not existing_user.is_email_verified:
                    return create_response(
                        message="User with this email already exists but email is not verified. Please verify your email to continue.",
                        status=False,
                        error_code=VALIDATION_ERROR_CODE,
                        status_code=400,
                        data={
                            "is_user_exists": True,
                            "signup_verified": False,
                            "email": signup_request.email,
                            "next_step": "verify_email"
                        }
                    )
                else:
                    return create_response(
                        message="User with this email already exists",
                        status=False,
                        error_code=VALIDATION_ERROR_CODE,
                        status_code=400
                    )

            # First, register the user with AWS Cognito
            # Use email as username for Cognito
            cognito_response = sign_up_user(
                password=signup_request.password,
                email=signup_request.email
            )

            # If Cognito registration was successful, save user to our database
            if cognito_response['status']:
                # Get the role ID — use requested role or default to 'user'
                from users.rbac.schema import get_role_id
                from users.decorators import VALID_ROLES
                requested_role = signup_request.role or "user"
                if requested_role.lower() not in VALID_ROLES:
                    return create_response(
                        message=f"Invalid role '{requested_role}'. Valid roles: {', '.join(sorted(VALID_ROLES))}",
                        status=False,
                        error_code=VALIDATION_ERROR_CODE,
                        status_code=400
                    )
                user_role_id = get_role_id(requested_role, create_if_missing=True)

                # Create user in our database
                user_data = {
                    "user_id": cognito_response['user_id'],
                    "email": signup_request.email,
                    "password": signup_request.password,
                    "auth_provider": "cognito",
                    "role_id": user_role_id  # Add role_id to user data
                }
                user_id = create_user(
                    data=user_data,
                    is_email_verified=False,
                    is_active=False
                )

                if user_id:
                    # Return success response with user_id
                    return create_response(
                        message=(
                            "User registered successfully. "
                            "Please check your email for verification code."
                        ),
                        status=True,
                        error_code=SUCCESS_CODE,
                        data={
                            "user_id": str(user_id),
                            "email": signup_request.email,
                            "next_step": "verify_email"
                        }
                    )
                else:
                    # Database save failed, rollback by deleting Cognito user
                    logger.error(
                        "Database user creation failed for "
                        f"{signup_request.email}, rolling back Cognito user"
                    )

                    # Attempt to delete the user from Cognito
                    delete_response = delete_cognito_user(signup_request.email)
                    if delete_response['status']:
                        logger.info(
                            "Successfully rolled back Cognito user for "
                            f"{signup_request.email}"
                        )
                    else:
                        logger.error(
                            "Failed to rollback Cognito user for "
                            f"{signup_request.email}: "
                            f"{delete_response['message']}"
                        )

                    return create_response(
                        message="Registration failed. Please try again.",
                        status=False,
                        error_code=SOMETHING_WENT_WRONG,
                        status_code=500,
                        description=(
                            "User creation failed - transaction rolled back"
                        )
                    )

            # Cognito registration failed
            return create_response(
                message=cognito_response['message'],
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
                description="Cognito registration failed"
            )

        except Exception as e:
            logger.exception(f"Error during signup: {e}")
            return create_response(
                message="An error occurred during signup",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(user_auth_route)
class VerifySignupView:
    @user_auth_route.post("/verify-signup")
    def post(self, email: str, confirmation_code: str):
        try:
            # Verify the user's email with Cognito
            # Use email as username for Cognito verification
            verification_response = confirm_signup(
                email, confirmation_code
            )

            if verification_response['status']:
                # Update user verification status in our database
                update_success = update_user_verification_status(
                    email=email,
                    is_verified=True,
                    is_active=True
                )

                if update_success:
                    # Successful verification and database update
                    return create_response(
                        message=(
                            "Email verification successful. "
                            "Your account is now active."
                        ),
                        status=True,
                        error_code=SUCCESS_CODE,
                        data={
                            "email": email,
                            "is_verified": True,
                            "is_active": True,
                            "next_step": "login"
                        }
                    )
                else:
                    # Cognito verification succeeded but database update failed
                    return create_response(
                        message=(
                            "Email verification successful "
                            "but failed to update account status. "
                            "Please contact support."
                        ),
                        status=False,
                        error_code=SOMETHING_WENT_WRONG,
                        description="Database update failed",
                        status_code=500
                    )
            else:
                # Failed verification
                return create_response(
                    message=verification_response['message'],
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    description="Verification failed",
                    status_code=400
                )

        except Exception as e:
            logger.exception(f"Error during email verification: {e}")
            return create_response(
                message="An error occurred during verification",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(user_auth_route)
class ResendVerificationView:
    @user_auth_route.post("/resend-verification")
    def post(self, email: str):
        try:
            # Check if user exists
            user = get_user_by_email(email)
            if not user:
                return create_response(
                    message="User with this email does not exist",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=404
                )

            # Resend verification code using email as username
            resend_response = resend_confirmation_code(email)

            if resend_response['status']:
                # Successful resend
                return create_response(
                    message="Verification code sent to your email address.",
                    status=True,
                    error_code=SUCCESS_CODE,
                    data={"email": email}
                )
            else:
                # Failed resend
                return create_response(
                    message=resend_response['message'],
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    description="Failed to resend verification code",
                    status_code=400
                )

        except Exception as e:
            logger.exception(f"Error during resend verification: {e}")
            return create_response(
                message="An error occurred while resending verification code",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(user_auth_route)
class LoginView:
    @user_auth_route.post("/login")
    def post(self, login_request: LoginRequest):
        try:
            # Handle MFA verification if requested
            if login_request.verification:
                return self._handle_mfa_verification(login_request)

            # Validate user and check login eligibility
            user_validation_response = self._validate_user_for_login(
                login_request.email
            )
            if user_validation_response:
                return user_validation_response

            # Get validated user
            user = get_user_by_email(login_request.email)

            # Authenticate with Cognito and handle response
            return self._handle_cognito_authentication(login_request, user)

        except Exception as e:
            logger.exception(f"Error during login: {e}")
            return create_response(
                message="An error occurred during login",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    def _handle_mfa_verification(self, login_request: LoginRequest):
        """Handle MFA verification flow"""
        # Get user info for MFA verification response
        user = get_user_by_email(login_request.email)
        if not user:
            return create_response(
                message="User not found",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=404
            )

        # Check if OAuth user trying to verify MFA for email/password login
        oauth_response = self._check_oauth_user_restriction(user)
        if oauth_response:
            return oauth_response

        # Perform EMAIL_OTP verification
        verification_resp = verify_login(
            login_request.session, login_request.otp,
            login_request.email  # Use email instead of username
        )

        if verification_resp['status']:
            return self._create_successful_login_response(
                verification_resp, user,
                "Email OTP verification successful. Login completed."
            )
        else:
            return create_response(
                message=verification_resp.get(
                    'message', 'Email OTP verification failed'
                ),
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                description="Email OTP verification failed",
                status_code=400
            )

    def _validate_user_for_login(self, email: str):
        """
        Validate user exists and can login.
        Returns error response if validation fails, None if valid.
        """
        # Check if user exists in our database
        user = get_user_by_email(email)
        if not user:
            return create_response(
                message="Invalid email or password",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
                data={
                    "is_user_exists": False
                }
            )

        # Check if OAuth user trying to login with email/password
        oauth_response = self._check_oauth_user_restriction(user)
        if oauth_response:
            return oauth_response

        # Check if user is verified
        if not user.is_email_verified:
            return create_response(
                message="Your email address is not verified. Please verify your email to continue with login.",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=403,
                data={
                    "is_user_exists": True,
                    "signup_verified": False,
                    "email": email,
                    "next_step": "verify_email"
                }
            )

        # Check if user is active
        if not user.is_active:
            return create_response(
                message="Your account is deactivated. Please contact support.",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=403
            )

        return None  # Validation passed

    def _check_oauth_user_restriction(self, user):
        """Check if OAuth user is trying to use email/password login"""
        if user.is_oauth_user:
            provider_name = user.auth_provider.value.title()
            return create_response(
                message=(
                    f"This account was created using {provider_name}. "
                    f"Please use {provider_name} to sign in."
                ),
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400,
                data={
                    "auth_provider": user.auth_provider.value,
                    "next_step": f"login_with_{user.auth_provider.value}"
                }
            )
        return None

    def _handle_cognito_authentication(
        self, login_request: LoginRequest, user
    ):
        """Handle Cognito authentication and process response"""
        # Authenticate with AWS Cognito using email as username
        cognito_response = cognito_login(
            username=login_request.email,
            password=login_request.password
        )

        if cognito_response['status']:
            return self._process_successful_cognito_response(
                cognito_response, user
            )
        else:
            return self._handle_cognito_error(cognito_response)

    def _process_successful_cognito_response(self, cognito_response, user):
        """Process successful Cognito response and check for MFA requirement"""
        # Check if MFA is required (session returned instead of tokens)
        if (
            'session' in cognito_response and
            'access_token' not in cognito_response
        ):
            # EMAIL_OTP is required - return session for OTP verification
            return create_response(
                message=(
                    "Email verification required. "
                    "Please enter the OTP sent to your email address."
                ),
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "session": cognito_response['session'],
                    "user_id": str(user.user_id),
                    "email": user.email,
                    "mfa_required": True,
                    "next_step": "verify_mfa"
                }
            )
        else:
            # No MFA required - return tokens directly
            return self._create_successful_login_response(
                cognito_response, user, "Login successful"
            )

    def _create_successful_login_response(
        self, cognito_response, user, message
    ):
        """Create successful login response with user data"""
        user_id = str(user.user_id)
        onboarded = get_is_onboarded(user_id)

        # Get user role information from UserProfile
        from users.rbac.schema import get_user_role_info
        user_role_info = get_user_role_info(user_id)

        # Determine role - return null if user has no role assignment in UserProfile
        role = None
        organization_id = None
        business_id = None

        if user_role_info:
            role = user_role_info.get("role_name")
            organization_id = user_role_info.get("organization_id")
            business_id = user_role_info.get("business_id")

        # Fallback to Cognito role if no UserProfile role exists (for backward compatibility)
        if not role:
            role = onboarded.get("role") if onboarded else None

        # Get full_name from user profile
        full_name = None
        if user.profile:
            first_name = user.profile.first_name or ""
            last_name = user.profile.last_name or ""
            full_name = f"{first_name} {last_name}".strip() or None

        # Update user agent preferences manually (Temporary)
        session = ScopedSession()
        try:
            predefined_agents = session.query(Agent).filter(Agent.type == "predefined").all()
            # Extract agent IDs while session is still open
            agent_ids = [str(agent.id) for agent in predefined_agents]
        except Exception as e:
            logger.error(f"Error getting predefined agents: {e}")
            agent_ids = []
        finally:
            session.close()
            ScopedSession.remove()

        # Set preferences after session is closed
        for agent_id in agent_ids:
            try:
                set_user_agent_preference(user_id, agent_id, None, None, None, on_login=True)
            except Exception as e:
                logger.error(f"Error setting preference for agent {agent_id}: {e}")

        return create_response(
            message=message,
            status=True,
            error_code=SUCCESS_CODE,
            data={
                **cognito_response,
                "user_id": user_id,
                "email": user.email,
                "full_name": full_name,
                "has_profile": user.has_profile,
                "is_onboarded": onboarded.get("is_onboarded") if onboarded else False,
                "role": role,  # Now returns null for users without role assignments
                "organization_id": organization_id,
                "business_id": business_id,
                "mfa_required": False,
                "next_step": (
                    "create_profile"
                    if not user.has_profile else "dashboard"
                )
            }
        )

    def _handle_cognito_error(self, cognito_response):
        """Handle Cognito authentication errors"""
        error_message = cognito_response.get('message', 'Login failed')

        # For incorrect password or general auth failures,
        # return generic message
        if (
            'incorrect' in error_message.lower()
            or 'password' in error_message.lower()
        ):
            return create_response(
                message="Invalid email or password",
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400
            )
        else:
            # For other Cognito errors, return the specific error
            return create_response(
                message=error_message,
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                description="Authentication failed",
                status_code=400
            )


@cbv(user_auth_route)
class RefreshTokenView:
    @user_auth_route.post("/refresh-token")
    def post(self, refresh_token_req: RefreshTokenRequest):
        try:
            resp = refresh_token(refresh_token_req.refresh_token)

            # Enrich response with user role from the new access token
            try:
                from users.auth import verify_jwt_token
                from users.rbac.schema import get_user_role_info
                claims = verify_jwt_token(resp.get("access_token", ""))
                user_id = claims.get("sub")
                if user_id:
                    role_info = get_user_role_info(user_id)
                    resp["role"] = role_info.get("role_name") if role_info else None
            except Exception as role_err:
                logger.warning(f"Could not attach role to refresh response: {role_err}")

            return create_response(
                message="Token refresh successful",
                status=True,
                data=resp
            )
        except HTTPException as e:
            logger.error(e)
            return create_response(
                message=e.detail,
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=e.status_code
            )
        except Exception as e:
            logger.exception(e)
            return create_response(
                message="Something went wrong, please try again later",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(user_auth_route)
class SocialLoginView:
    @user_auth_route.get("/social-auth/login/")
    def get(self, provider: str = Query(..., description="Social provider: google or facebook")):
        """
        Initiate social login with Google or Facebook via Cognito
        Returns the OAuth URL for frontend to redirect to
        """
        try:
            provider = provider.capitalize()

            allowed_providers = {"Google", "Facebook"}
            if provider not in allowed_providers:
                return create_response(
                    message=f"Unsupported provider '{provider}'. Must be one of {allowed_providers}.",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )
            # Generate social login URL
            url_response = generate_social_login_url(provider)

            if url_response['status']:
                return create_response(
                    message=(
                        "login URL generated successfully"
                    ),
                    status=True,
                    error_code=SUCCESS_CODE,
                    data={
                        "login_url": url_response['login_url']
                    }
                )
            else:
                return create_response(
                    message=url_response['message'],
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

        except Exception as e:
            logger.exception(f"Error initiating login: {e}")
            return create_response(
                message="Failed to initiate social login",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )


@cbv(user_auth_route)
class SocialCallbackView:
    @user_auth_route.get("/social-auth/callback")
    def get(self, code: str = None):
        """
        Handle OAuth callback from Cognito after social login
        Always returns JSON response with tokens and user data
        """
        try:
            if not code:
                logger.error("No authorization code provided in callback")
                return self._redirect_with_error("Authorization failed - no code provided")

            # Exchange authorization code for tokens
            token_response = exchange_oauth_code_for_tokens(code)
            if not token_response['status']:
                return self._redirect_with_error(token_response['message'])
            # Extract user info from ID token
            user_info_response = extract_user_info_from_id_token(
                token_response.get('id_token')
            )
            if not user_info_response['status']:
                return self._redirect_with_error(user_info_response['message'])

            user_info = user_info_response['user_info']

            # Create or get user in database
            user_result = self._create_or_get_social_user(user_info)
            if not user_result['success']:
                return self._redirect_with_error(user_result['message'])

            access_token = token_response.get('access_token')
            refresh_token = token_response.get('refresh_token')

            # Build redirect URL with tokens
            params = {
                'access_token': access_token,
            }
            if refresh_token:
                params['refresh_token'] = refresh_token

            query_string = urlencode(params)
            redirect_url = f"{FRONTEND_URL}/social-login?{query_string}"
            return RedirectResponse(url=redirect_url)

        except Exception as e:
            logger.exception(f"Error in social login callback: {e}")
            return create_response(
                message="Social login failed",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )
        
    def _redirect_with_error(self, message: str):
        """
        Redirect user to frontend with error message in query string.
        """
        params = urlencode({"error": message})
        return RedirectResponse(f"{FRONTEND_URL}/social-login?error={params}")

    def _create_or_get_social_user(self, user_info: dict) -> dict:
        """
        Create or get existing social user in database
        """
        try:
            email = user_info['email']
            cognito_user_id = user_info['cognito_user_id']

            # Check if user already exists
            existing_user = get_user_by_email(email)
            cognito_data = get_cognito_username_by_user_id(cognito_user_id, fetch_name=True)

            username = cognito_data.get('username')
            first_name = cognito_data.get('first_name')
            last_name = cognito_data.get('last_name')

            if existing_user:
                # User exists - check if it's the same auth provider
                if (
                    existing_user.auth_provider.value
                    != user_info['auth_provider']
                ):
                    delete_response = delete_cognito_user(username)
                    logger.info(f"User delete status: {delete_response}")

                    return {
                        'success': False,
                        'message': (
                            "Account with this email already exists using "
                            f"{existing_user.auth_provider.value}."
                            f"Please use {existing_user.auth_provider.value} "
                            "to sign in."
                        )
                    }

                # Same provider - return existing user
                return {
                    'success': True,
                    'user_id': existing_user.user_id,
                    'has_profile': existing_user.has_profile,
                    'message': 'User logged in successfully'
                }

            # Get role_id for "user" role
            from users.rbac.schema import get_role_id
            user_role_id = get_role_id("user", create_if_missing=True)

            # Create new user
            user_data = {
                "user_id": user_info['cognito_user_id'],
                "email": email,
                "password": None,  # No password for social users
                "auth_provider": user_info['auth_provider'],
                "role_id": user_role_id,  # Add role_id
                "first_name": first_name,  # Add first_name
                "last_name": last_name  # Add last_name
            }

            # Set Cognito custom attributes for social users (is_onboarded and role)
            update_result = update_cognito_user_attributes(
                username=username,
                attributes={
                    'custom:role': 'user',
                    'custom:is_onboarded': 'false'
                }
            )
            if not update_result['status']:
                logger.warning(
                    f"Failed to set Cognito custom attributes for {email}: "
                    f"{update_result['message']}"
                )

            user_id = create_user(
                data=user_data,
                is_email_verified=True,  # Social login emails are pre-verified
                is_active=True  # Social users are immediately active
            )

            if user_id:
                logger.info(
                    "Created new social user: "
                    f"{email} via {user_info['auth_provider']}"
                )
                return {
                    'success': True,
                    'user_id': user_id,
                    'has_profile': False,  # New users don't have profile yet
                    'message': 'User created and logged in successfully'
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to create user account'
                }

        except Exception as e:
            logger.exception(f"Error creating/getting social user: {e}")
            return {
                'success': False,
                'message': 'Database error occurred'
            }


def _get_user_response_data(user_id: str) -> dict:
    """
    Helper function to build user response data.
    Reused by login and /me endpoints.

    Args:
        user_id: User ID

    Returns:
        Dictionary with user data
    """
    from users.rbac.schema import get_user_role_info
    from prism_inspire.db.session import ScopedSession
    from users.models.user import Users
    from sqlalchemy.orm import joinedload

    session = ScopedSession()
    try:
        user = session.query(Users).options(
            joinedload(Users.profile)
        ).filter(Users.user_id == user_id).first()

        if not user:
            return None

        # Get onboarding status from Cognito
        onboarded = get_is_onboarded(user_id)

        # Get user role information from UserProfile
        user_role_info = get_user_role_info(user_id)

        # Determine role - return null if user has no role assignment
        role = None
        organization_id = None
        business_id = None

        if user_role_info:
            role = user_role_info.get("role_name")
            organization_id = user_role_info.get("organization_id")
            business_id = user_role_info.get("business_id")

        # Fallback to Cognito role if no UserProfile role exists
        if not role:
            role = onboarded.get("role") if onboarded else None

        # Get full_name from user profile
        full_name = None
        first_name = None
        last_name = None
        date_of_birth = None
        additional_info = None

        if user.profile:
            first_name = user.profile.first_name
            last_name = user.profile.last_name
            full_name = f"{first_name or ''} {last_name or ''}".strip() or None
            date_of_birth = user.profile.date_of_birth.isoformat() if user.profile.date_of_birth else None
            additional_info = user.profile.additional_info

        # Determine if password change is allowed (only for cognito users)
        password_change_allowed = user.auth_provider.value == "cognito"

        return {
            "user_id": user_id,
            "email": user.email,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": date_of_birth,
            "additional_info": additional_info,
            "has_profile": user.has_profile,
            "is_onboarded": str(onboarded.get("is_onboarded")) if onboarded else "false",
            "role": role,
            "organization_id": organization_id,
            "business_id": business_id,
            "password_change_allowed": password_change_allowed
        }
    finally:
        session.close()
        ScopedSession.remove()


@user_auth_route.get("/me")
def get_me(user_data: dict = Depends(verify_token)):
    """
    Get authenticated user's info from access_token header.

    Requires 'access-token' header with valid JWT token.

    Returns:
        User information including:
        - user_id: User ID
        - email: User email
        - full_name: Combined first and last name
        - first_name: User first name
        - last_name: User last name
        - date_of_birth: User date of birth (ISO format)
        - additional_info: Additional user information
        - has_profile: Boolean indicating if user has profile
        - is_onboarded: String indicating onboarding status
        - role: User role
        - organization_id: Organization ID
        - business_id: Business ID
        - mfa_required: Boolean indicating if MFA is required
        - next_step: Next step for the user
        - password_change_allowed: Boolean indicating if password change is allowed
    """
    try:
        user_id = user_data.get("sub")
        response_data = _get_user_response_data(user_id)

        if not response_data:
            raise HTTPException(status_code=404, detail="User not found")

        return JSONResponse(
            content={
                "status": True,
                "message": "User info fetched successfully",
                "data": response_data
            }
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@cbv(user_auth_route)
class ResetPasswordView:
    @user_auth_route.post("/request-password-reset")
    def request_password_reset(self, request: RequestPasswordResetRequest):
        """
        Step 1: Request password reset - sends email with JWT reset token

        This endpoint initiates the password reset flow by:
        - Creating a JWT token with 15-minute expiration
        - Sending an email with reset link to user
        - No database storage needed - token is self-contained
        """
        try:
            # Check if user exists and is active (for security, always return success)
            user = get_user_by_email(request.email)

            if user and user.is_active:
                # Create JWT reset token with 15-minute expiration
                reset_token = create_reset_token(
                    email=request.email,
                    expires_minutes=15
                )

                # Get user name for email personalization (optional)
                user_name = None
                if hasattr(user, 'profile') and user.profile:
                    user_name = getattr(user.profile, 'name', None)

                # Send password reset email using existing function
                email_result = send_password_reset_email(
                    recipient_email=request.email,
                    reset_token=reset_token,
                    user_name=user_name
                )

                logger.info(f"Password reset email sending to: {request.email} and status is {email_result.get('status')}")
            else:
                # User doesn't exist or inactive - still return success for security
                logger.warning(f"Password reset requested for non-existent/inactive user: {request.email}")

            # Always return success for security (don't reveal if email exists)
            return create_response(
                message="If an account with this email exists, you will receive a password reset link shortly.",
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "email": request.email,
                    "reset_requested": True
                }
            )

        except Exception as e:
            logger.error(f"Error requesting password reset for {request.email}: {str(e)}")
            return create_response(
                message="An error occurred while processing your request. Please try again.",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @user_auth_route.post("/reset-password")
    def reset_password(self, reset_request: ResetPasswordRequest):
        """
        Step 2: Complete password reset using JWT token from email

        This endpoint completes the password reset flow by:
        - Validating the JWT reset token from email
        - Setting new password in Cognito and database
        - Using existing password update functions
        """
        try:
            # Validate JWT reset token
            token_data = verify_reset_token(reset_request.reset_token)

            if not token_data:
                return create_response(
                    message="Invalid or expired reset token",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=401
                )

            email = token_data.get("email")
            if not email:
                return create_response(
                    message="Invalid reset token format",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

            # Verify user still exists and is active
            user = get_user_by_email(email)
            if not user or not user.is_active:
                return create_response(
                    message="User account not found or inactive",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=404
                )

            # Password confirmation is already validated by the Pydantic model
            # Set new password in Cognito using reusable function
            password_result = admin_set_user_password(
                username=email,
                password=reset_request.new_password,
                permanent=True
            )

            if not password_result.get('status'):
                return create_response(
                    message=f"Failed to reset password: {password_result.get('message')}",
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=500
                )

            # Update password in database using reusable function
            db_update_success = update_user_password(email, reset_request.new_password)

            if not db_update_success:
                logger.warning(f"Failed to update password in database for {email} - Cognito updated successfully")
                return create_response(
                    message="Password updated in authentication system but failed to sync with database. Please contact support.",
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=500
                )

            logger.info(f"Password reset completed successfully for user: {email}")

            return create_response(
                message="Password reset successfully. You can now login with your new password.",
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "email": email,
                    "password_reset": True,
                    "cognito_updated": True,
                    "database_updated": True
                }
            )

        except ValueError as e:
            # This catches the password mismatch validation from Pydantic
            return create_response(
                message=str(e),
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400
            )

        except Exception as e:
            logger.error(f"Error completing password reset: {str(e)}")
            return create_response(
                message="An error occurred while resetting password. Please try again.",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )

    @user_auth_route.post("/change-password")
    def change_password(self, change_request: ChangePasswordRequest, user_data: dict = Depends(verify_token)):
        """
        Change password for authenticated users

        This endpoint allows authenticated users to change their password by providing:
        - Current password (for verification)
        - New password
        - Confirm password (must match new password)

        The function reuses existing schema functions and Cognito utilities.
        """
        try:
            user_email = user_data.get("email")
            if not user_email:
                return create_response(
                    message="User email not found in token",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

            # Get user from database
            user = get_user_by_email(user_email)
            if not user:
                return create_response(
                    message="User not found",
                    status=False,
                    error_code=NOT_FOUND,
                    status_code=404
                )

            # Verify current password from database
            logger.info(f"Verifying current password for user: {user_email}")
            if not user.password:
                logger.warning(f"No password found in database for user {user_email}")
                return create_response(
                    message="Password change not available for this account type.",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

            password_matches = check_password_hash(change_request.current_password, user.password)
            logger.info(f"Current password verification result: {password_matches}")

            if not password_matches:
                logger.warning(f"Failed password verification for user {user_email}: Password does not match")
                return create_response(
                    message="Current password is incorrect. Please verify and try again.",
                    status=False,
                    error_code=VALIDATION_ERROR_CODE,
                    status_code=400
                )

            # Password confirmation is already validated by the Pydantic model
            # Set new password in Cognito using reusable function
            password_result = admin_set_user_password(
                username=user_email,
                password=change_request.new_password,
                permanent=True
            )

            if not password_result.get('status'):
                return create_response(
                    message="Failed to change password",
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    description=password_result.get('message'),
                    status_code=500
                )

            # Update password in database using reusable function
            db_update_success = update_user_password(user_email, change_request.new_password)

            if not db_update_success:
                logger.warning(f"Failed to update password in database for {user_email} - Cognito updated successfully")
                return create_response(
                    message="Password updated in authentication system but failed to sync with database. Please contact support.",
                    status=False,
                    error_code=SOMETHING_WENT_WRONG,
                    status_code=500
                )

            logger.info(f"Password changed successfully for user: {user_email}")

            return create_response(
                message="Password changed successfully.",
                status=True,
                error_code=SUCCESS_CODE,
                data={
                    "email": user_email,
                    "password_changed": True,
                    "cognito_updated": True,
                    "database_updated": True
                }
            )

        except ValueError as e:
            return create_response(
                message=str(e),
                status=False,
                error_code=VALIDATION_ERROR_CODE,
                status_code=400
            )

        except Exception as e:
            logger.error(f"Error changing password for {user_email}: {str(e)}")
            return create_response(
                message="An error occurred while changing password. Please try again.",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=500
            )
