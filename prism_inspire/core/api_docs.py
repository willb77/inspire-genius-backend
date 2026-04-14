from __future__ import annotations

"""
OpenAPI metadata, tag definitions, security schemes, and role
permission mappings for the Inspire Genius API.

This module is loaded by ``prism_inspire/main.py`` to enrich the
auto-generated OpenAPI spec served at ``/api/docs`` (Swagger UI),
``/api/redoc`` (ReDoc), and ``/api/openapi.json``.
"""

# ── OpenAPI metadata ──────────────────────────────────────────────────────

API_METADATA: dict = {
    "title": "Inspire Genius API",
    "description": (
        "## Inspire Genius — AI Coaching Platform\n\n"
        "REST & WebSocket APIs powering the Inspire Genius multi-role "
        "coaching platform.  The backend is built with **FastAPI**, "
        "**SQLAlchemy**, **LangChain**, and **Milvus** (vector DB).\n\n"
        "### Authentication\n"
        "All protected endpoints require an `access-token` header containing "
        "a JWT issued by AWS Cognito (or Magic Auth in development).  Use the "
        "`/v1/login` endpoint to obtain tokens.\n\n"
        "### Roles\n"
        "| Role | Description |\n"
        "|------|-------------|\n"
        "| `user` | End-user / employee receiving coaching |\n"
        "| `manager` | Team lead with direct-report visibility |\n"
        "| `company-admin` | Organization-level administrator |\n"
        "| `practitioner` | PRISM-accredited coach |\n"
        "| `distributor` | Regional PRISM credit wholesaler |\n"
        "| `super-admin` | Platform owner — full access |\n"
    ),
    "version": "2.0.0",
    "docs_url": "/api/docs",
    "redoc_url": "/api/redoc",
    "openapi_url": "/api/openapi.json",
}

# ── Tag descriptions ──────────────────────────────────────────────────────
# Order here controls display order in Swagger UI / ReDoc.

API_TAGS: list[dict] = [
    # ── Authentication & Users ────────────────────────────────────────
    {
        "name": "User Authentication",
        "description": "Signup, login, OTP verification, token refresh, "
                       "password reset, social login (Google / Facebook).",
    },
    {
        "name": "User Management",
        "description": "Invite users, assign roles, edit profiles, "
                       "bulk invite — requires admin or super-admin role.",
    },
    {
        "name": "RBAC",
        "description": "Role, group, and permission CRUD — super-admin only.",
    },
    {
        "name": "RBAC Relationships",
        "description": "Assign / revoke permissions on roles and groups.",
    },
    {
        "name": "Onboarding",
        "description": "Create and update user profiles during the "
                       "post-registration onboarding flow.",
    },
    # ── Organization & Licensing ──────────────────────────────────────
    {
        "name": "Organization Management",
        "description": "Create, update, and deactivate organizations and "
                       "businesses.  Assign AI agents to orgs/businesses.",
    },
    {
        "name": "License Management",
        "description": "Create and manage subscription licenses "
                       "(tiers, status, org assignment).",
    },
    # ── AI Agents & Chat ──────────────────────────────────────────────
    {
        "name": "Agent Settings",
        "description": "Configure AI coaching agents — voices, tones, "
                       "accents, user preferences, and agent CRUD.",
    },
    {
        "name": "Agent Services",
        "description": "WebSocket endpoints for real-time AI agent "
                       "interactions (Alex, PRISM Coach, Career Coach, "
                       "Training Coach).",
    },
    {
        "name": "Chat Management",
        "description": "Conversation CRUD, message history, PDF export "
                       "of chat transcripts.",
    },
    {
        "name": "Meridian AI Mentor",
        "description": "Unified Meridian AI mentor — intent classification, "
                       "domain routing, and specialist agent dispatch.",
    },
    # ── Documents & Media ─────────────────────────────────────────────
    {
        "name": "File Service",
        "description": "Upload, list, download, and delete documents.  "
                       "Files are vectorized for semantic search via Milvus.",
    },
    {
        "name": "Audio Service",
        "description": "Audio file download, text-to-speech streaming, "
                       "and WebSocket-based real-time audio.",
    },
    {
        "name": "Frontend Text Management",
        "description": "Retrieve and manage UI text content served to "
                       "the frontend by route and CSS selector.",
    },
    # ── Dashboards & Analytics ────────────────────────────────────────
    {
        "name": "Dashboard & Analytics",
        "description": "Organization, business, and license statistics "
                       "for admin dashboards.",
    },
    {
        "name": "User Dashboard",
        "description": "Personal stats, goals, and training progress — "
                       "any authenticated user.",
    },
    {
        "name": "Cost Dashboard",
        "description": "Token and API cost analytics scoped by role — "
                       "managers and above.",
    },
    {
        "name": "Analytics",
        "description": "Aggregated platform analytics — role-scoped access.",
    },
    {
        "name": "Reports",
        "description": "Generate, list, and download analytical reports.",
    },
    {
        "name": "Data Export",
        "description": "Bulk data export with async background jobs.",
    },
    # ── Role-Specific ─────────────────────────────────────────────────
    {
        "name": "Manager",
        "description": "Team management, hiring, training oversight — "
                       "requires manager role.",
    },
    {
        "name": "Company Admin",
        "description": "Organization-wide management, departments, "
                       "user oversight — requires company-admin role.",
    },
    {
        "name": "Practitioner",
        "description": "Client management, coaching sessions, PRISM "
                       "tools — requires practitioner role.",
    },
    {
        "name": "Distributor",
        "description": "Territory management, practitioner network, "
                       "credit allocation — requires distributor role.",
    },
    # ── Feedback & Prompts ────────────────────────────────────────────
    {
        "name": "Feedback",
        "description": "Submit and manage RLHF feedback on AI responses — "
                       "any authenticated user.",
    },
    {
        "name": "Feedback Admin",
        "description": "Feedback aggregation, review, and corrections — "
                       "super-admin only.",
    },
    {
        "name": "Prompt Management",
        "description": "Prompt template versioning and A/B testing — "
                       "super-admin only.",
    },
    # ── Support ───────────────────────────────────────────────────────
    {
        "name": "Issue Reporting",
        "description": "Create, track, and comment on support issues.  "
                       "Admins can update status and add internal notes.",
    },
]

# ── Security schemes ─────────────────────────────────────────────────────

SECURITY_SCHEMES: dict = {
    "AccessToken": {
        "type": "apiKey",
        "in": "header",
        "name": "access-token",
        "description": "JWT access token from login or refresh endpoint",
    }
}

# ── Role permissions per endpoint group ───────────────────────────────────
# "*" means public (no auth required).  Listed roles are the minimum required.

_ALL_ROLES = ["user", "manager", "company-admin", "practitioner", "distributor", "super-admin"]
_ADMIN_UP = ["company-admin", "practitioner", "distributor", "super-admin"]
_MANAGER_UP = ["manager", "company-admin", "practitioner", "distributor", "super-admin"]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    # Auth & Users
    "User Authentication": ["*"],
    "User Management": ["company-admin", "super-admin"],
    "RBAC": ["super-admin"],
    "RBAC Relationships": ["super-admin"],
    "Onboarding": _ALL_ROLES,
    # Organization & Licensing
    "Organization Management": _ADMIN_UP,
    "License Management": _ADMIN_UP,
    # AI Agents & Chat
    "Agent Settings": _ALL_ROLES,
    "Agent Services": _ALL_ROLES,
    "Chat Management": _ALL_ROLES,
    "Meridian AI Mentor": _ALL_ROLES,
    # Documents & Media
    "File Service": _ALL_ROLES,
    "Audio Service": _ALL_ROLES,
    "Frontend Text Management": ["*"],
    # Dashboards & Analytics
    "Dashboard & Analytics": _MANAGER_UP,
    "User Dashboard": _ALL_ROLES,
    "Cost Dashboard": _MANAGER_UP,
    "Analytics": _MANAGER_UP,
    "Reports": _MANAGER_UP,
    "Data Export": _ADMIN_UP,
    # Role-Specific
    "Manager": ["manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Company Admin": ["company-admin", "practitioner", "distributor", "super-admin"],
    "Practitioner": ["practitioner", "distributor", "super-admin"],
    "Distributor": ["distributor", "super-admin"],
    # Feedback & Prompts
    "Feedback": _ALL_ROLES,
    "Feedback Admin": ["super-admin"],
    "Prompt Management": ["super-admin"],
    # Support
    "Issue Reporting": _ALL_ROLES,
}
