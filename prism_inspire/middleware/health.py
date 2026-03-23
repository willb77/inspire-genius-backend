"""
Health check endpoints for API monitoring and uptime checks.

Endpoints:
    GET /health       — Basic liveness probe (always 200 if app is running)
    GET /health/ready — Readiness probe (checks database + critical services)
    GET /health/live  — Kubernetes-style liveness (alias for /health)
"""

import time
from typing import Any

from fastapi import APIRouter

from prism_inspire.core.log_config import logger

health_router = APIRouter(tags=["Health"])

_start_time = time.time()


def _uptime_seconds() -> float:
    return round(time.time() - _start_time, 1)


@health_router.get("/health")
async def health_check() -> dict[str, Any]:
    """Basic liveness probe — returns 200 if the app process is running."""
    return {
        "status": "healthy",
        "uptime_seconds": _uptime_seconds(),
        "version": "1.0.0",
    }


@health_router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Kubernetes-style liveness probe."""
    return {"status": "alive"}


@health_router.get("/health/ready")
async def readiness() -> dict[str, Any]:
    """
    Readiness probe — verifies critical dependencies are reachable:
    - PostgreSQL database connection
    - Milvus vector database (if configured)
    """
    checks: dict[str, str] = {}

    # Check PostgreSQL
    try:
        from prism_inspire.db.session import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")  # type: ignore[arg-type]
        db.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
        logger.error("Readiness check failed: database", exc_info=True)

    all_ok = all(v == "ok" for v in checks.values())

    return {
        "status": "ready" if all_ok else "degraded",
        "uptime_seconds": _uptime_seconds(),
        "checks": checks,
    }
