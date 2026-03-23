from __future__ import annotations

"""
Input validation and sanitization middleware.

Provides XSS sanitization, file upload validation, and common input
format validators (UUID, email, pagination).
"""

import json
import logging
import re
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── Allowed file upload settings ──────────────────────────────────────────

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".doc", ".docx", ".xlsx", ".csv", ".json",
    ".png", ".jpg", ".jpeg",
}

ALLOWED_CONTENT_TYPES: set[str] = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/json",
    "image/png",
    "image/jpeg",
}

MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

# ── Regex patterns for sanitization ───────────────────────────────────────

_SCRIPT_TAG_RE = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_SCRIPT_OPEN_RE = re.compile(r"<script[^>]*>", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script>", re.IGNORECASE)
_EVENT_HANDLER_RE = re.compile(
    r"\s*on\w+\s*=\s*[\"'][^\"']*[\"']",
    re.IGNORECASE,
)
_JAVASCRIPT_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ── Sanitization helpers ──────────────────────────────────────────────────


def sanitize_string(value: str) -> str:
    """
    Strip potential XSS payloads from a string value.

    Removes:
    - ``<script>...</script>`` blocks
    - Inline event handlers (``onclick``, ``onerror``, etc.)
    - ``javascript:`` URLs
    """
    original = value
    value = _SCRIPT_TAG_RE.sub("", value)
    value = _SCRIPT_OPEN_RE.sub("", value)
    value = _SCRIPT_CLOSE_RE.sub("", value)
    value = _EVENT_HANDLER_RE.sub("", value)
    value = _JAVASCRIPT_URL_RE.sub("", value)

    if value != original:
        logger.info("Sanitized input string (removed potential XSS)")

    return value.strip()


def _sanitize_value(value: Any) -> Any:
    """Recursively sanitize strings in dicts, lists, and scalars."""
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


# ── File upload validation ────────────────────────────────────────────────


def validate_file_upload(
    filename: str, content_type: str, size_bytes: int
) -> tuple[bool, str]:
    """
    Validate a file upload against extension, MIME-type, and size rules.

    Returns:
        (is_valid, error_message) — error_message is empty when valid.
    """
    # Extension check
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False, f"File extension '{ext}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

    # Content-type check (also accept vnd.openxmlformats-* variants)
    type_ok = content_type in ALLOWED_CONTENT_TYPES or content_type.startswith(
        "application/vnd.openxmlformats-officedocument."
    )
    if not type_ok:
        return False, f"Content type '{content_type}' is not allowed."

    # Size check
    if size_bytes > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        return False, f"File size exceeds maximum of {max_mb:.0f} MB."

    return True, ""


# ── Common format validators ──────────────────────────────────────────────


def validate_uuid(value: str) -> bool:
    """Return True if *value* is a valid UUID (any version)."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def validate_email_format(value: str) -> bool:
    """Return True if *value* matches a basic email pattern."""
    return bool(_EMAIL_RE.match(value))


def validate_pagination(page: int, limit: int) -> tuple[int, int]:
    """
    Enforce sane pagination defaults.

    Returns (page, limit) clamped to:
    - page >= 1
    - 1 <= limit <= 100
    """
    page = max(1, page)
    limit = max(1, min(100, limit))
    return page, limit


# ── Middleware ─────────────────────────────────────────────────────────────


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that sanitizes string values in JSON request
    bodies and query parameters.

    Skips ``multipart/form-data`` requests (file uploads) to avoid
    corrupting binary payloads.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_type = request.headers.get("content-type", "")

        # Skip file uploads
        if "multipart/form-data" in content_type:
            return await call_next(request)

        # Sanitize JSON body
        if "application/json" in content_type:
            try:
                body = await request.body()
                if body:
                    data = json.loads(body)
                    sanitized = _sanitize_value(data)
                    if sanitized != data:
                        logger.info(
                            "Sanitized JSON body for %s %s",
                            request.method,
                            request.url.path,
                        )
                    # Replace the request body with sanitized version
                    request._body = json.dumps(sanitized).encode("utf-8")
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # Let the endpoint handle malformed JSON

        # Sanitize query parameters (logged but not mutated — query params
        # are immutable on the Starlette Request object; endpoints should
        # use the validator helpers directly).
        for key, value in request.query_params.items():
            sanitized_val = sanitize_string(value)
            if sanitized_val != value:
                logger.warning(
                    "Potentially unsafe query param '%s' on %s %s",
                    key,
                    request.method,
                    request.url.path,
                )

        return await call_next(request)
