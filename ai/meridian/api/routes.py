from __future__ import annotations

import uuid
from typing import Optional
from fastapi import APIRouter, Depends
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.response import (
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    create_response,
)
from ai.meridian.api.schemas import (
    MeridianChatRequest,
    MeridianFeedbackRequest,
)
from ai.meridian.api.service import MeridianService


meridian_routes = APIRouter(
    prefix="/meridian",
    tags=["Meridian AI Mentor"],
)

# Singleton service — initialized on first use
_service: Optional[MeridianService] = None


def _get_service() -> MeridianService:
    global _service
    if _service is None:
        _service = MeridianService()
    return _service


@meridian_routes.post("/chat", summary="Send a message to Meridian",
                      description="Meridian classifies intent, routes to the appropriate domain "
                                  "orchestrator, dispatches to specialist agents, and returns "
                                  "a unified response.")
async def chat(
    request: MeridianChatRequest,
    user_data: dict = Depends(verify_token),
):
    """
    Send a message to Meridian.

    Meridian classifies intent, routes to the appropriate domain orchestrator,
    dispatches to specialist agents, and returns a unified response. The user
    never sees individual agent identities.
    """
    try:
        user_id = user_data.get("sub")
        if not user_id:
            return create_response(
                message="Authentication required",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=401,
            )

        session_id = request.session_id or str(uuid.uuid4())
        service = _get_service()

        result = await service.chat(
            user_id=user_id,
            session_id=session_id,
            message=request.message,
        )

        return create_response(
            message="Success",
            status=True,
            data={
                "session_id": session_id,
                "response": result["response"],
                "intent": result.get("intent"),
            },
        )

    except Exception as e:
        logger.error(f"Meridian chat error: {e}")
        return create_response(
            message="Something went wrong, please try again later",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )


@meridian_routes.get("/history", summary="Get Meridian session history",
                     description="Retrieve the conversation history for a Meridian session. "
                                 "Individual agent identities are never exposed.")
async def get_history(
    session_id: str,
    user_data: dict = Depends(verify_token),
):
    """
    Get conversation history for a session.

    Users see only Meridian responses — individual agent identities
    are never exposed.
    """
    try:
        user_id = user_data.get("sub")
        if not user_id:
            return create_response(
                message="Authentication required",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=401,
            )

        service = _get_service()
        history = service.get_history(session_id=session_id, user_id=user_id)

        if history is None:
            return create_response(
                message="Session not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        return create_response(
            message="Success",
            status=True,
            data={
                "session_id": session_id,
                "messages": history,
            },
        )

    except Exception as e:
        logger.error(f"Meridian history error: {e}")
        return create_response(
            message="Something went wrong",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )


@meridian_routes.post("/feedback", summary="Submit RLHF feedback",
                      description="Submit feedback (thumbs-up/down, correction, flag) on a Meridian "
                                  "response. Corrections become high-priority memory entries.")
async def submit_feedback(
    request: MeridianFeedbackRequest,
    user_data: dict = Depends(verify_token),
):
    """
    Submit RLHF feedback on a Meridian response.

    Corrections are stored as high-priority memory entries (priority=10)
    that influence future agent behavior.
    """
    try:
        user_id = user_data.get("sub")
        if not user_id:
            return create_response(
                message="Authentication required",
                status=False,
                error_code=SOMETHING_WENT_WRONG,
                status_code=401,
            )

        service = _get_service()
        entry_id = await service.submit_feedback(
            user_id=user_id,
            session_id=request.session_id,
            message_content=request.message_content,
            correction=request.correction,
            rating=request.rating,
        )

        return create_response(
            message="Feedback recorded — thank you, this helps me improve",
            status=True,
            data={"feedback_id": entry_id},
        )

    except Exception as e:
        logger.error(f"Meridian feedback error: {e}")
        return create_response(
            message="Something went wrong",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )


@meridian_routes.get("/agents")
async def list_agents(
    user_data: dict = Depends(verify_token),
):
    """
    List available agent capabilities.

    This endpoint is for admin/debug purposes — it exposes the internal
    agent roster. Not user-facing in the UI.
    """
    try:
        service = _get_service()
        agents = service.list_agent_capabilities()

        return create_response(
            message="Success",
            status=True,
            data={"agents": agents},
        )

    except Exception as e:
        logger.error(f"Meridian agents list error: {e}")
        return create_response(
            message="Something went wrong",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
