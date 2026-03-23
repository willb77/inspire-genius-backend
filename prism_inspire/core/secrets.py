"""
AWS Secrets Manager utility with in-memory caching and .env fallback.

Usage:
    from prism_inspire.core.secrets import get_secret

    db_url = await get_secret("inspire-genius/DATABASE_URL")
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[str, float]] = {}
_DEFAULT_TTL_SECONDS = 300  # 5 minutes


def _is_development() -> bool:
    """Check if running in local development (no Secrets Manager)."""
    return os.getenv("APP_ENV", "development") == "development"


def _get_from_env(secret_name: str) -> str | None:
    """Fall back to process.env — strip any path prefix to get the env var name."""
    # "inspire-genius/DATABASE_URL" -> "DATABASE_URL"
    env_key = secret_name.rsplit("/", 1)[-1]
    return os.getenv(env_key)


async def get_secret(secret_name: str, ttl: int = _DEFAULT_TTL_SECONDS) -> str:
    """
    Retrieve a secret by name.

    In development: reads from environment variables (dotenv).
    In production: fetches from AWS Secrets Manager with in-memory TTL cache.

    Args:
        secret_name: The secret name or ARN. For env fallback, the part after
                     the last "/" is used as the env var name.
        ttl: Cache time-to-live in seconds (default 300).

    Returns:
        The secret string value.

    Raises:
        ValueError: If the secret cannot be found.
    """
    # Development fallback
    if _is_development():
        value = _get_from_env(secret_name)
        if value is not None:
            return value
        raise ValueError(
            f"Secret '{secret_name}' not found in environment. "
            f"Set {secret_name.rsplit('/', 1)[-1]} in your .env file."
        )

    # Check cache
    if secret_name in _cache:
        cached_value, cached_at = _cache[secret_name]
        if time.time() - cached_at < ttl:
            return cached_value

    # Fetch from AWS Secrets Manager
    try:
        import boto3
        from botocore.exceptions import ClientError

        client = boto3.client(
            "secretsmanager",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
        response = client.get_secret_value(SecretId=secret_name)

        # Handle both string and binary secrets
        if "SecretString" in response:
            secret_value = response["SecretString"]
        else:
            import base64
            secret_value = base64.b64decode(response["SecretBinary"]).decode("utf-8")

        # If it's a JSON object, try to extract a single value
        try:
            parsed: Any = json.loads(secret_value)
            if isinstance(parsed, dict) and len(parsed) == 1:
                secret_value = str(next(iter(parsed.values())))
        except (json.JSONDecodeError, StopIteration):
            pass

        # Cache it
        _cache[secret_name] = (secret_value, time.time())
        logger.info("Fetched secret '%s' from Secrets Manager", secret_name)
        return secret_value

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error(
            "Failed to fetch secret '%s': %s — %s",
            secret_name,
            error_code,
            e.response["Error"]["Message"],
        )
        raise ValueError(f"Could not retrieve secret '{secret_name}': {error_code}") from e


def clear_cache() -> None:
    """Clear the in-memory secrets cache (useful for testing)."""
    _cache.clear()


def get_secret_sync(secret_name: str, ttl: int = _DEFAULT_TTL_SECONDS) -> str:
    """
    Synchronous version of get_secret for use in Settings/startup code.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an async context — use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run, get_secret(secret_name, ttl)
            ).result()
    else:
        return asyncio.run(get_secret(secret_name, ttl))
