from fastapi import FastAPI
from prism_inspire.core.config import settings
from fastapi.middleware.cors import CORSMiddleware
# Router imports
from users.auth_service.user_auth import user_auth_route as user_auth_router
from users.auth_service.user_management import user_management_routes as user_management_router
from users.rbac.rbac_routes import rbac_route as rbac_router
from users.rbac.rbac_relationships import rbac_relationship_route as rbac_relationship_router
from users.onboarding.onboarding import onboarding_route
from ai.agent_settings.onboarding import agents_settings as agents_settings_router
from ai.file_services.file_service import file_service as file_service_router
from ai.audio_services.audio_service import audio_service as audio_service_router
from ai.ai_agent_services.agent_services.agent_services import agent_services as agent_services_router
from ai.chat_services.chat_routes import chat_routes as chat_routes_router
from users.organization.organization import organization_routes
from users.license.license import license_routes
from users.dashboard.dashboard import dashboard_routes
from users.issues.issues import issue_routes
from ai.file_services.vector_utils.startup import startup_event, shutdown_event
from ai.frontend_text_services.frontend_text_service import frontend_text_routes
# Phase 2 role-specific routers
from users.manager.routes import manager_routes
from users.company_admin.routes import company_admin_routes
from users.practitioner.routes import practitioner_routes
from users.distributor.routes import distributor_routes
# Meridian AI Mentor
from ai.meridian.api.routes import meridian_routes as meridian_router


app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=settings.DOCS_URL,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include app routers
app.include_router(user_auth_router, prefix=settings.API_V1_STR, tags=["User Authentication"])
app.include_router(user_management_router, prefix=settings.API_V1_STR, tags=["User Management"])
app.include_router(rbac_router, prefix=settings.API_V1_STR, tags=["RBAC"])
app.include_router(rbac_relationship_router, prefix=settings.API_V1_STR, tags=["RBAC Relationships"])
app.include_router(onboarding_route, prefix=settings.API_V1_STR, tags=["Onboarding"])
app.include_router(agents_settings_router, prefix=settings.API_V1_STR, tags=["Agent Settings"])
app.include_router(file_service_router, prefix=settings.API_V1_STR, tags=["File Service"])
app.include_router(agent_services_router, prefix=settings.API_V1_STR, tags=["Agent Services"])
app.include_router(chat_routes_router, prefix=settings.API_V1_STR, tags=["Chat Management"])
app.include_router(organization_routes, prefix=settings.API_V1_STR, tags=["Organization Management"])
app.include_router(license_routes, prefix=settings.API_V1_STR, tags=["License Management"])
app.include_router(dashboard_routes, prefix=settings.API_V1_STR, tags=["Dashboard & Analytics"])
app.include_router(issue_routes, prefix=settings.API_V1_STR, tags=["Issue Reporting"])
app.include_router(frontend_text_routes, prefix=settings.API_V1_STR, tags=["Frontend Text Management"])
app.include_router(audio_service_router, prefix=settings.API_V1_STR, tags=["Audio Service"])
# Phase 2 role-specific routers
app.include_router(manager_routes, prefix=settings.API_V1_STR, tags=["Manager"])
app.include_router(company_admin_routes, prefix=settings.API_V1_STR, tags=["Company Admin"])
app.include_router(practitioner_routes, prefix=settings.API_V1_STR, tags=["Practitioner"])
app.include_router(distributor_routes, prefix=settings.API_V1_STR, tags=["Distributor"])
# Meridian AI Mentor
app.include_router(meridian_router, prefix=settings.API_V1_STR, tags=["Meridian AI Mentor"])

# Startup and shutdown events for optimal performance
@app.on_event("startup")
async def startup():
    """Initialize connection pools and resources on startup."""
    await startup_event()

@app.on_event("shutdown") 
async def shutdown():
    """Clean up resources on shutdown."""
    await shutdown_event()

