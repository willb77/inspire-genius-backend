# Security Posture — Inspire Genius Backend

## Authentication

- **Primary provider**: AWS Cognito with RS256 JWT tokens
- **Fallback provider**: Magic Auth with HS256 JWT for development/testing
- Token verification in `users/auth.py` inspects the `kid` header to distinguish provider
- Access tokens passed via `access-token` HTTP header
- Refresh tokens support single-flight renewal to prevent race conditions

## Authorization

- **RBAC with 6-role hierarchy**: user, manager, company-admin, practitioner, distributor, super-admin
- Role hierarchy enforced in `users/decorators.py` via `require_role()` and `require_role_or_above()`
- Route-level protection with `require_authenticated_user()` and `require_admin_role()` decorators
- Role permissions documented per endpoint group in `prism_inspire/core/api_docs.py`

## Rate Limiting

- In-memory sliding-window rate limiter (`prism_inspire/middleware/rate_limiter.py`)
- Per-endpoint configuration:
  - Login: 5 requests / 60 seconds
  - Signup: 3 requests / 60 seconds
  - Verification / resend: 5 requests / 60 seconds
  - Password reset request: 3 requests / 60 seconds
  - Authenticated API calls: 100 requests / 60 seconds
  - Anonymous API calls: 30 requests / 60 seconds
- Key derivation: user ID (from JWT `sub` claim) for authenticated requests, client IP for anonymous
- Returns HTTP 429 with `Retry-After` header when exceeded
- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers on all responses

## Input Validation

- **XSS sanitization**: middleware strips `<script>` tags, inline event handlers (`onclick`, `onerror`, etc.), and `javascript:` URLs from all JSON string values
- **Parameterized queries**: all database access uses SQLAlchemy ORM — no raw SQL string interpolation
- **File upload restrictions**: extension whitelist (.pdf, .doc, .docx, .xlsx, .csv, .json, .png, .jpg, .jpeg), MIME-type validation, 10 MB size limit
- **Format validators**: UUID, email, pagination range enforcement
- **Pydantic models**: request body validation with type checking, min/max length, and custom validators

## Security Headers

All HTTP responses include:

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

The `Server` header is stripped to reduce fingerprinting.

## CORS

- Whitelist-only configuration loaded from `ALLOWED_ORIGINS` environment variable
- Wildcard `*` triggers a warning log; not used in production
- Origin validation rejects malformed URLs

## Error Handling

- **Production mode** (`APP_ENV=production`): unhandled exceptions return generic HTTP 500 with no stack trace or internal details
- **Development mode**: error detail and traceback included in response for debugging
- Full tracebacks always logged server-side regardless of environment
- Sentry integration for real-time error tracking (when `SENTRY_DSN` configured)

## Encryption & Transport

- HTTPS enforced via HSTS header (1-year max-age with preload)
- URL security validation rejects non-localhost HTTP URLs in configuration
- Sensitive tokens stored via encrypted storage on the client side
- AWS credentials managed through IAM / environment variables, never hardcoded

## Findings

No high or critical security findings. The security posture covers OWASP Top 10 categories including injection, broken authentication, XSS, security misconfiguration, and sensitive data exposure.
