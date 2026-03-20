from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class MeridianChatRequest(BaseModel):
    """Request body for POST /meridian/chat."""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None  # auto-generated if not provided


class MeridianChatResponse(BaseModel):
    """Response from Meridian chat."""
    session_id: str
    response: str
    intent: Optional[dict[str, Any]] = None
    agent_results: list[dict[str, Any]] = Field(default_factory=list)


class MeridianHistoryEntry(BaseModel):
    """A single entry in conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None


class MeridianFeedbackRequest(BaseModel):
    """Request body for POST /meridian/feedback."""
    session_id: str
    message_content: str  # the response being corrected
    correction: str = Field(..., min_length=1, max_length=5000)
    rating: Optional[int] = Field(None, ge=1, le=5)


class AgentCapabilityResponse(BaseModel):
    """Response for GET /meridian/agents."""
    agent_id: str
    name: str
    tagline: str
    domain: str
    actions: list[str]
    description: str
    is_active: bool
