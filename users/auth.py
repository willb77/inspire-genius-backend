from jose import jwt, JWTError, jwk
import requests
import base64
from fastapi import Header, HTTPException
from datetime import datetime, timedelta, timezone
from prism_inspire.core.log_config import logger
import boto3
from prism_inspire.core.config import settings
from users.aws_wrapper.cognito_utils import get_is_onboarded
from typing import Optional


COGNITO_REGION = settings.AWS_REGION
USER_POOL_ID = settings.COGNITO_USER_POOL_ID
CLIENT_ID = settings.COGNITO_CLIENT_ID
CLIENT_SECRET = settings.COGNITO_CLIENT_SECRET
COGNITO_ISSUER = (f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
                  f"{USER_POOL_ID}")
JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"
COGNITO_DOMAIN = settings.COGNITO_DOMAIN
COGNITO_TOKEN_URL = f"{COGNITO_DOMAIN}/oauth2/token"

# JWT settings for password reset tokens
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"

JWKS = requests.get(JWKS_URL).json()


def verify_jwt_token(token: str, access_token: str = None) -> dict:
    """
    Verify JWT token signature and return claims

    Args:
        token: JWT token to verify
        access_token: Access token for at_hash validation (optional)

    Returns:
        Decoded token claims

    Raises:
        JWTError: If token verification fails
    """
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header["kid"]
    key_data = next((k for k in JWKS["keys"] if k["kid"] == kid), None)

    if key_data is None:
        raise JWTError("Public key not found")

    public_key = jwk.construct(key_data)

    # Decode with or without access_token for at_hash validation
    if access_token:
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=COGNITO_ISSUER,
            access_token=access_token
        )
    else:
        # For ID tokens without access_token, skip at_hash validation
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=COGNITO_ISSUER,
            options={"verify_at_hash": False}
        )
    return claims


def verify_id_token(id_token: str, access_token: str = None) -> dict:
    """
    Verify ID token specifically (with optional at_hash validation)

    Args:
        id_token: ID token to verify
        access_token: Access token for at_hash validation (optional)

    Returns:
        Decoded token claims

    Raises:
        JWTError: If token verification fails
    """
    return verify_jwt_token(id_token, access_token)


def verify_token(
    access_token: str = Header(..., alias="access-token")
):
    try:
        # Use the reusable JWT verification function
        claims = verify_jwt_token(access_token)
        user_info = {
            "sub": claims.get("sub"),
            "groups": claims.get("cognito:groups", [])
        }

        # Try to fetch user attributes from Cognito
        # This may fail for social login tokens due to scope limitations
        try:
            client = boto3.client(
                "cognito-idp", region_name=COGNITO_REGION
            )
            user_data = client.get_user(AccessToken=access_token)

            # Extract custom:role if available
            for attr in user_data["UserAttributes"]:
                if attr["Name"] == "custom:role":
                    user_info["user_role"] = attr["Value"]
                    break
        except Exception as cognito_error:
            # If get_user fails (e.g., for social login tokens),
            # extract what we can from the JWT claims
            if "NotAuthorizedException" in str(cognito_error):
                # For social login tokens, try to get role from JWT claims
                user_info["role"] = claims.get("custom:role", "None")
            else:
                # For other errors, re-raise
                raise cognito_error
        onboard_info = get_is_onboarded(user_info["sub"])
        user_info["is_onboarded"] = onboard_info.get("is_onboarded")
        user_info["email"] = onboard_info.get("email", user_info.get("email"))
        user_info["user_role"] = onboard_info.get("role", user_info.get("role"))
        return user_info

    except JWTError as e:
        raise HTTPException(
            status_code=401, detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        # Handle other exceptions (like Cognito errors)
        raise HTTPException(
            status_code=401, detail=f"Token verification failed: {str(e)}"
        )


def refresh_token(
    token: str
):
    basic_auth = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    ).decode()

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {basic_auth}"
    }

    data = {
        "grant_type": "refresh_token",
        # "client_id": CLIENT_ID,
        "refresh_token": token
    }

    response = requests.post(COGNITO_TOKEN_URL, data=data, headers=headers)
    if response.status_code != 200:
        logger.error(f"Cognito token refresh failed: {response.text}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired refresh token"
        )

    return response.json()


def verify_websocket_token(token: str) -> dict:
    """
    Verify WebSocket authentication token
    
    Args:
        token: JWT access token
        
    Returns:
        User data dict with sub and groups
        
    Raises:
        JWTError: If token verification fails
    """
    try:
        claims = verify_jwt_token(token)
        user_info = {
            "sub": claims.get("sub"),
            "groups": claims.get("cognito:groups", [])
        }
        return user_info
    except JWTError as e:
        raise JWTError(f"Token verification failed: {str(e)}")


def create_reset_token(email: str, expires_minutes: int = 15) -> Optional[str]:
    """
    Create a JWT token for password reset with expiration

    Args:
        email: User email address
        expires_minutes: Token expiration in minutes (default: 15)

    Returns:
        JWT token string or None if creation fails
    """
    try:
        # Create payload with email and expiration
        payload = {
            "email": email,
            "type": "password_reset",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
            "iat": datetime.now(timezone.utc)
        }

        # Create JWT token
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        logger.info(f"Password reset token created for: {email}")
        return token

    except Exception as e:
        logger.error(f"Error creating reset token: {e}")
        return None


def verify_reset_token(token: str) -> Optional[dict]:
    """
    Verify and decode password reset JWT token

    Args:
        token: JWT token string

    Returns:
        Dictionary with token data if valid, None if invalid/expired
    """
    try:
        # Decode and verify JWT token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if it's a password reset token
        if payload.get("type") != "password_reset":
            logger.warning("Invalid token type for password reset")
            return None

        # Check if token has expired (JWT handles this automatically)
        # If expired, jwt.decode will raise ExpiredSignatureError

        return {
            "email": payload.get("email"),
            "type": payload.get("type"),
            "exp": payload.get("exp"),
            "iat": payload.get("iat")
        }

    except jwt.ExpiredSignatureError:
        logger.warning("Password reset token has expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid password reset token: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying reset token: {e}")
        return None
