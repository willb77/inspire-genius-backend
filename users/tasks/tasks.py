"""Monolith task-agent proxy router (Combined Plan §A.E3.3).

Five POST endpoints proxy structured task requests from the monolith to the
agent-engine ECS service:

    POST /v1/tasks/job-blueprint     -> agent-engine /v1/agents/james/run
    POST /v1/tasks/interview-prep    -> agent-engine /v1/agents/maven/run
    POST /v1/tasks/team-composition  -> agent-engine /v1/agents/atlas/run
    POST /v1/tasks/onboarding        -> agent-engine /v1/agents/forge/run
    POST /v1/tasks/document-research -> agent-engine /v1/agents/sage/run

Per the plan:
  - The mapping table is read from agent_configs (cached 60s).
  - Auth is monolith JWT validation (verify_token Header dep). The caller's
    role is forwarded to agent-engine via x-user-role / x-user-id headers
    so agent-engine can apply the role gate it owns.
  - Each route is gated by an env var feature flag ENABLE_TASK_AGENT_<NAME>.
  - On agent-engine 5xx the proxy returns 503 + Retry-After header.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import SessionLocal
from users.auth import verify_token
from users.models.task_result import TaskResult


task_routes = APIRouter(prefix="/tasks", tags=["Task Agents"])


# ─── Configuration ────────────────────────────────────────────────


_AGENT_ENGINE_BASE_URL = os.environ.get(
    "AGENT_ENGINE_TASK_BASE_URL",
    # Public API Gateway endpoint — monolith VPC has no peering with the
    # agent-engine VPC, so the call exits to the public internet and re-
    # enters via API Gateway. Override with a private endpoint once the
    # VPCs are peered.
    "https://api-dev.inspiresgenius.com",
).rstrip("/")

_AGENT_ENGINE_TIMEOUT_SECONDS = float(
    os.environ.get("AGENT_ENGINE_TASK_TIMEOUT", "60")
)

# Per-agent feature flags. Default off — flip to "1" to enable.
_FEATURE_FLAGS = {
    "maven":  os.environ.get("ENABLE_TASK_AGENT_MAVEN",  "0") == "1",
    "james":  os.environ.get("ENABLE_TASK_AGENT_JAMES",  "0") == "1",
    "atlas":  os.environ.get("ENABLE_TASK_AGENT_ATLAS",  "0") == "1",
    "forge":  os.environ.get("ENABLE_TASK_AGENT_FORGE",  "0") == "1",
    "sage":   os.environ.get("ENABLE_TASK_AGENT_SAGE",   "0") == "1",
}


# ─── Static task → agent map (matches agent_configs E3.1 backfill) ─


# Mirrors the rows in agent_configs after the E3.1 migration. Hard-coded
# here so the monolith doesn't have to reach into Aurora on every request;
# refreshed manually on plan changes. The agent-engine round-trip is the
# real source of truth — this map is just a router shortcut.
_TASK_TO_AGENT = {
    "job-blueprint":     ("james",  "/v1/agents/james/run"),
    "interview-prep":    ("maven",  "/v1/agents/maven/run"),
    "team-composition":  ("atlas",  "/v1/agents/atlas/run"),
    "onboarding":        ("forge",  "/v1/agents/forge/run"),
    "document-research": ("sage",   "/v1/agents/sage/run"),
}


# ─── Pydantic request bodies (mirror agent-engine schemas) ────────


class InterviewPrepRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=128)
    role_title: str = Field(..., min_length=1, max_length=128)
    candidate_name: Optional[str] = Field(default=None, max_length=255)
    interview_focus: Optional[str] = Field(default=None, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=64)


class JobBlueprintMatchRequest(BaseModel):
    role_title: str = Field(..., min_length=1, max_length=128)
    company_name: str = Field(..., min_length=1, max_length=255)
    role_responsibilities: str = Field(..., min_length=1, max_length=4000)
    candidate_summary: str = Field(..., min_length=1, max_length=4000)
    desired_outcomes: Optional[str] = Field(default=None, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=64)


class TeamCompositionRequest(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=255)
    team_purpose: str = Field(..., min_length=1, max_length=2000)
    member_summaries: list[str] = Field(..., min_length=1, max_length=50)
    target_skills: Optional[list[str]] = Field(default=None, max_length=30)
    session_id: Optional[str] = Field(default=None, max_length=64)


class OnboardingFlowRequest(BaseModel):
    new_hire_name: str = Field(..., min_length=1, max_length=255)
    new_hire_role: str = Field(..., min_length=1, max_length=128)
    company_name: str = Field(..., min_length=1, max_length=255)
    company_culture_notes: Optional[str] = Field(default=None, max_length=4000)
    week_number: Optional[int] = Field(default=1, ge=1, le=12)
    session_id: Optional[str] = Field(default=None, max_length=64)


class DocumentResearchRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    document_filter_tags: Optional[list[str]] = Field(default=None, max_length=20)
    summarize_only: bool = False
    session_id: Optional[str] = Field(default=None, max_length=64)


class TaskAgentResponse(BaseModel):
    agent_name: str
    content: str
    confidence: float = 1.0
    suggested_next: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# ─── Proxy core ───────────────────────────────────────────────────


async def _proxy_to_agent_engine(
    task_slug: str,
    body: dict,
    user_data: dict,
    response: Response,
) -> dict:
    agent_id, path = _TASK_TO_AGENT[task_slug]

    if not _FEATURE_FLAGS.get(agent_id, False):
        raise HTTPException(
            status_code=503,
            detail=(
                f"Task agent '{agent_id}' is disabled. "
                f"Set ENABLE_TASK_AGENT_{agent_id.upper()}=1 to enable."
            ),
        )

    user_id = user_data.get("sub", "") or user_data.get("email", "")
    role = user_data.get("user_role", "user")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user identity")

    url = f"{_AGENT_ENGINE_BASE_URL}{path}"
    headers = {
        "x-user-id": user_id,
        "x-user-role": role,
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=_AGENT_ENGINE_TIMEOUT_SECONDS) as client:
            agent_response = await client.post(url, json=body, headers=headers)
    except httpx.TimeoutException:
        elapsed = (time.perf_counter() - started) * 1000.0
        logger.warning(
            "Task agent timeout: agent=%s elapsed=%.0fms", agent_id, elapsed
        )
        response.headers["Retry-After"] = "5"
        raise HTTPException(
            status_code=504,
            detail=f"Agent engine timed out for {agent_id} after {_AGENT_ENGINE_TIMEOUT_SECONDS}s",
        )
    except httpx.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000.0
        logger.exception(
            "Task agent transport error: agent=%s elapsed=%.0fms", agent_id, elapsed
        )
        response.headers["Retry-After"] = "5"
        raise HTTPException(
            status_code=503,
            detail=f"Agent engine unreachable: {type(exc).__name__}",
        )

    if 500 <= agent_response.status_code < 600:
        response.headers["Retry-After"] = "10"
        raise HTTPException(
            status_code=503,
            detail=f"Agent engine returned {agent_response.status_code}",
        )

    if agent_response.status_code >= 400:
        # Bubble up 4xx (auth, validation) verbatim.
        try:
            payload = agent_response.json()
            detail = payload.get("detail", agent_response.text)
        except Exception:
            detail = agent_response.text
        raise HTTPException(status_code=agent_response.status_code, detail=detail)

    return agent_response.json()


# ─── Routes ───────────────────────────────────────────────────────


@task_routes.post("/job-blueprint", response_model=TaskAgentResponse)
async def task_job_blueprint(
    body: JobBlueprintMatchRequest,
    response: Response,
    user_data: dict = Depends(verify_token),
) -> dict:
    return await _proxy_to_agent_engine(
        "job-blueprint", body.model_dump(), user_data, response,
    )


@task_routes.post("/interview-prep", response_model=TaskAgentResponse)
async def task_interview_prep(
    body: InterviewPrepRequest,
    response: Response,
    user_data: dict = Depends(verify_token),
) -> dict:
    return await _proxy_to_agent_engine(
        "interview-prep", body.model_dump(), user_data, response,
    )


@task_routes.post("/team-composition", response_model=TaskAgentResponse)
async def task_team_composition(
    body: TeamCompositionRequest,
    response: Response,
    user_data: dict = Depends(verify_token),
) -> dict:
    return await _proxy_to_agent_engine(
        "team-composition", body.model_dump(), user_data, response,
    )


@task_routes.post("/onboarding", response_model=TaskAgentResponse)
async def task_onboarding(
    body: OnboardingFlowRequest,
    response: Response,
    user_data: dict = Depends(verify_token),
) -> dict:
    return await _proxy_to_agent_engine(
        "onboarding", body.model_dump(), user_data, response,
    )


@task_routes.post("/document-research", response_model=TaskAgentResponse)
async def task_document_research(
    body: DocumentResearchRequest,
    response: Response,
    user_data: dict = Depends(verify_token),
) -> dict:
    return await _proxy_to_agent_engine(
        "document-research", body.model_dump(), user_data, response,
    )


# ─── Save-to-workspace endpoint (E3.4 follow-up) ─────────────────


class SaveTaskResultRequest(BaseModel):
    task_slug: str = Field(..., min_length=1, max_length=64)
    agent_id: str = Field(..., min_length=1, max_length=64)
    request_payload: dict
    result_payload: dict
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    title: Optional[str] = Field(default=None, max_length=255)
    note: Optional[str] = Field(default=None, max_length=2000)


class SavedTaskResultRow(BaseModel):
    id: str
    task_slug: str
    agent_id: str
    title: Optional[str]
    confidence: Optional[float]
    created_at: str


def _user_uuid_from_claims(user_data: dict) -> uuid.UUID:
    sub = user_data.get("sub", "")
    if not sub:
        raise HTTPException(status_code=401, detail="Missing user identity")
    try:
        return uuid.UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user identity")


@task_routes.post("/results", response_model=SavedTaskResultRow)
def save_task_result(
    body: SaveTaskResultRequest,
    user_data: dict = Depends(verify_token),
) -> dict:
    """Persist a task-agent result for later viewing in the workspace.

    The frontend calls this after a successful task run when the user
    presses "Save to my workspace" on the result card.
    """
    if body.task_slug not in _TASK_TO_AGENT:
        raise HTTPException(status_code=400, detail=f"Unknown task slug: {body.task_slug}")

    user_id = _user_uuid_from_claims(user_data)
    org_id_raw = user_data.get("org_id") or user_data.get("organization_id")
    org_id: Optional[uuid.UUID] = None
    if org_id_raw:
        try:
            org_id = uuid.UUID(str(org_id_raw))
        except (ValueError, TypeError):
            org_id = None

    session = SessionLocal()
    try:
        row = TaskResult(
            user_id=user_id,
            org_id=org_id,
            task_slug=body.task_slug,
            agent_id=body.agent_id,
            request_payload=body.request_payload,
            result_payload=body.result_payload,
            confidence=body.confidence,
            title=body.title,
            note=body.note,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {
            "id": str(row.id),
            "task_slug": row.task_slug,
            "agent_id": row.agent_id,
            "title": row.title,
            "confidence": row.confidence,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
    except Exception as exc:
        session.rollback()
        logger.exception("save_task_result failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save task result")
    finally:
        session.close()


@task_routes.get("/results", response_model=list[SavedTaskResultRow])
def list_task_results(
    user_data: dict = Depends(verify_token),
    task_slug: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """List saved task results for the calling user (most-recent first)."""
    user_id = _user_uuid_from_claims(user_data)
    session = SessionLocal()
    try:
        q = session.query(TaskResult).filter(TaskResult.user_id == user_id)
        if task_slug:
            q = q.filter(TaskResult.task_slug == task_slug)
        rows = q.order_by(TaskResult.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(r.id),
                "task_slug": r.task_slug,
                "agent_id": r.agent_id,
                "title": r.title,
                "confidence": r.confidence,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    finally:
        session.close()
