from __future__ import annotations

"""
Phase 7 — API Hardening & Security tests.

Covers rate limiting, input validation/sanitization, security headers,
API documentation metadata, and role permission mappings.
"""

import time
import uuid

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 7.C1 Rate Limiting
# ═══════════════════════════════════════════════════════════════════════════


class TestRateLimitStore:
    """Unit tests for the in-memory RateLimitStore."""

    def test_under_limit_returns_allowed(self):
        from prism_inspire.middleware.rate_limiter import RateLimitStore

        store = RateLimitStore()
        allowed, remaining, retry_after = store.check("test-key", limit=5, window_seconds=60)
        assert allowed is True
        assert remaining == 4
        assert retry_after == 0

    def test_at_limit_returns_denied(self):
        from prism_inspire.middleware.rate_limiter import RateLimitStore

        store = RateLimitStore()
        key = "flood-key"
        for _ in range(5):
            store.check(key, limit=5, window_seconds=60)

        allowed, remaining, retry_after = store.check(key, limit=5, window_seconds=60)
        assert allowed is False
        assert remaining == 0
        assert retry_after > 0

    def test_cleanup_removes_expired_entries(self):
        from prism_inspire.middleware.rate_limiter import RateLimitStore

        store = RateLimitStore()
        key = "expire-key"
        # Inject an old timestamp manually
        store._store[key] = [time.time() - 200]
        store._cleanup(key)
        # Key should have been removed entirely
        assert key not in store._store

    def test_rate_limits_config_has_expected_keys(self):
        from prism_inspire.middleware.rate_limiter import RATE_LIMITS

        expected_keys = {
            "POST:/v1/login",
            "POST:/v1/signup",
            "POST:/v1/verify-signup",
            "POST:/v1/resend-verification",
            "POST:/v1/request-password-reset",
            "_default_authenticated",
            "_default_anonymous",
        }
        assert expected_keys.issubset(set(RATE_LIMITS.keys()))


# ═══════════════════════════════════════════════════════════════════════════
# 7.C2 Input Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestSanitizeString:
    """Tests for the sanitize_string helper."""

    def test_removes_script_tags(self):
        from prism_inspire.middleware.validation import sanitize_string

        result = sanitize_string('hello <script>alert("xss")</script> world')
        assert "<script>" not in result
        assert "alert" not in result

    def test_removes_event_handlers(self):
        from prism_inspire.middleware.validation import sanitize_string

        result = sanitize_string('<img src="x" onerror="alert(1)">')
        assert "onerror" not in result

    def test_preserves_normal_text(self):
        from prism_inspire.middleware.validation import sanitize_string

        text = "Hello, this is a normal sentence with no XSS."
        assert sanitize_string(text) == text


class TestValidateFileUpload:
    """Tests for file upload validation."""

    def test_rejects_exe(self):
        from prism_inspire.middleware.validation import validate_file_upload

        valid, msg = validate_file_upload("malware.exe", "application/x-msdownload", 1024)
        assert valid is False
        assert "not allowed" in msg.lower()

    def test_accepts_pdf(self):
        from prism_inspire.middleware.validation import validate_file_upload

        valid, msg = validate_file_upload("report.pdf", "application/pdf", 1024)
        assert valid is True
        assert msg == ""

    def test_rejects_oversized_files(self):
        from prism_inspire.middleware.validation import validate_file_upload

        huge = 20 * 1024 * 1024  # 20 MB
        valid, msg = validate_file_upload("big.pdf", "application/pdf", huge)
        assert valid is False
        assert "size" in msg.lower()


class TestFormatValidators:
    """Tests for UUID, email, and pagination validators."""

    def test_validate_uuid_accepts_valid(self):
        from prism_inspire.middleware.validation import validate_uuid

        assert validate_uuid(str(uuid.uuid4())) is True

    def test_validate_uuid_rejects_invalid(self):
        from prism_inspire.middleware.validation import validate_uuid

        assert validate_uuid("not-a-uuid") is False

    def test_validate_pagination_enforces_limits(self):
        from prism_inspire.middleware.validation import validate_pagination

        page, limit = validate_pagination(-5, 500)
        assert page == 1
        assert limit == 100

        page2, limit2 = validate_pagination(0, 0)
        assert page2 == 1
        assert limit2 == 1


# ═══════════════════════════════════════════════════════════════════════════
# 7.C3 Security Headers
# ═══════════════════════════════════════════════════════════════════════════


class TestSecurityHeaders:
    """Tests for security headers middleware and error handler."""

    def test_middleware_is_importable(self):
        from prism_inspire.middleware.security_headers import SecurityHeadersMiddleware

        assert SecurityHeadersMiddleware is not None

    def test_production_error_handler_is_importable(self):
        from prism_inspire.middleware.security_headers import ProductionErrorHandler

        handler = ProductionErrorHandler()
        assert callable(handler)


# ═══════════════════════════════════════════════════════════════════════════
# 7.C4 API Documentation
# ═══════════════════════════════════════════════════════════════════════════


class TestApiDocs:
    """Tests for OpenAPI metadata and security schemes."""

    def test_api_metadata_has_required_keys(self):
        from prism_inspire.core.api_docs import API_METADATA

        required = {"title", "description", "version", "docs_url", "redoc_url", "openapi_url"}
        assert required.issubset(set(API_METADATA.keys()))

    def test_api_tags_is_list_with_expected_length(self):
        from prism_inspire.core.api_docs import API_TAGS

        assert isinstance(API_TAGS, list)
        assert len(API_TAGS) == 14

    def test_security_schemes_has_access_token(self):
        from prism_inspire.core.api_docs import SECURITY_SCHEMES

        assert "AccessToken" in SECURITY_SCHEMES
        assert SECURITY_SCHEMES["AccessToken"]["type"] == "apiKey"

    def test_role_permissions_has_expected_tag_keys(self):
        from prism_inspire.core.api_docs import ROLE_PERMISSIONS, API_TAGS

        tag_names = {tag["name"] for tag in API_TAGS}
        permission_keys = set(ROLE_PERMISSIONS.keys())
        assert tag_names == permission_keys
