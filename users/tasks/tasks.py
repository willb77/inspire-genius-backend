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
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from prism_inspire.core.log_config import logger
from users.auth import verify_token


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
