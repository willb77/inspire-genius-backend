from __future__ import annotations

"""
OpenAPI metadata, tag definitions, security schemes, and role
permission mappings for the Inspire Genius API.
"""

# ── OpenAPI metadata ──────────────────────────────────────────────────────

API_METADATA: dict = {
    "title": "Inspire Genius API",
    "description": "AI coaching platform backend — multi-role APIs with RBAC",
    "version": "1.0.0",
    "docs_url": "/api/docs",
    "redoc_url": "/api/redoc",
    "openapi_url": "/api/openapi.json",
}

# ── Tag descriptions ──────────────────────────────────────────────────────

API_TAGS: list[dict] = [
    {"name": "User Authentication", "description": "Login, signup, token refresh, password management"},
    {"name": "User Management", "description": "User invitation, role assignment, CRUD"},
    {"name": "Manager", "description": "Team management, hiring, training — requires manager role"},
    {"name": "Company Admin", "description": "Organization management, departments — requires company-admin role"},
    {"name": "Practitioner", "description": "Client management, coaching sessions — requires practitioner role"},
    {"name": "Distributor", "description": "Territory, practitioner network, credits — requires distributor role"},
    {"name": "User Dashboard", "description": "Personal stats, goals, training — any authenticated user"},
    {"name": "Cost Dashboard", "description": "Cost analytics by scope — role-based access"},
    {"name": "Feedback", "description": "Submit and manage feedback — any authenticated user"},
    {"name": "Feedback Admin", "description": "Feedback aggregation, corrections — super-admin only"},
    {"name": "Prompt Management", "description": "Prompt template versioning — super-admin only"},
    {"name": "Analytics", "description": "Aggregated analytics — role-scoped access"},
    {"name": "Reports", "description": "Report generation and download"},
    {"name": "Data Export", "description": "Bulk data export with async jobs"},
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

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "User Authentication": ["*"],
    "User Management": ["admin", "super-admin"],
    "Manager": ["manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Company Admin": ["company-admin", "practitioner", "distributor", "super-admin"],
    "Practitioner": ["practitioner", "distributor", "super-admin"],
    "Distributor": ["distributor", "super-admin"],
    "User Dashboard": ["user", "manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Cost Dashboard": ["manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Feedback": ["user", "manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Feedback Admin": ["super-admin"],
    "Prompt Management": ["super-admin"],
    "Analytics": ["manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Reports": ["manager", "company-admin", "practitioner", "distributor", "super-admin"],
    "Data Export": ["company-admin", "practitioner", "distributor", "super-admin"],
}
