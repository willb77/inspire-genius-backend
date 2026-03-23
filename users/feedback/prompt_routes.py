from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict

from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession
from users.decorators import require_role, log_access
from users.models.feedback import PromptTemplate
from users.response import (
    create_response,
    SUCCESS_CODE,
    SOMETHING_WENT_WRONG,
    NOT_FOUND,
    VALIDATION_ERROR_CODE,
    FORBIDDEN_ERROR_CODE,
)

prompt_admin_routes = APIRouter(prefix="/admin/prompts", tags=["Prompt Management"])


@prompt_admin_routes.get("")
def list_prompts(
    agent_id: Optional[str] = Query(None, description="Filter by agent_id"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user_data: dict = Depends(require_role("super-admin")),
):
    """List prompt templates."""
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="list")

        query = session.query(PromptTemplate).filter(
            PromptTemplate.is_deleted.is_(False)
        )

        if agent_id:
            query = query.filter(PromptTemplate.agent_id == agent_id)
        if status:
            query = query.filter(PromptTemplate.status == status)

        total = query.count()
        offset = (page - 1) * limit
        records = query.order_by(PromptTemplate.name, PromptTemplate.version.desc()).offset(offset).limit(limit).all()

        items = [
            {
                "id": str(r.id),
                "name": r.name,
                "agent_id": str(r.agent_id) if r.agent_id else None,
                "version": r.version,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

        return create_response(
            message="Prompt templates retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={"items": items, "total": total, "page": page, "limit": limit},
        )
    except Exception as e:
        logger.error(f"Error listing prompts: {str(e)}")
        return create_response(
            message="Failed to retrieve prompt templates",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@prompt_admin_routes.post("")
def create_prompt(
    name: str,
    template_text: str,
    agent_id: Optional[str] = None,
    variables_json: Optional[str] = None,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Create a new prompt template."""
    creator_id = user_data.get("sub")
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="create")

        prompt = PromptTemplate(
            name=name,
            agent_id=agent_id,
            template_text=template_text,
            version=1,
            status="draft",
            variables_json=variables_json,
            created_by=creator_id,
        )
        session.add(prompt)
        session.commit()

        return create_response(
            message="Prompt template created successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(prompt.id),
                "name": prompt.name,
                "version": prompt.version,
                "status": prompt.status,
            },
            status_code=201,
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating prompt: {str(e)}")
        return create_response(
            message="Failed to create prompt template",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@prompt_admin_routes.put("/{prompt_id}")
def update_prompt(
    prompt_id: str,
    template_text: str,
    variables_json: Optional[str] = None,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Update a draft prompt template."""
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="update")

        prompt = session.query(PromptTemplate).filter(
            PromptTemplate.id == prompt_id,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        if not prompt:
            return create_response(
                message="Prompt template not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        if prompt.status != "draft":
            return create_response(
                message="Only draft prompts can be edited",
                status=False,
                error_code=FORBIDDEN_ERROR_CODE,
                status_code=400,
            )

        prompt.template_text = template_text
        if variables_json is not None:
            prompt.variables_json = variables_json

        session.commit()

        return create_response(
            message="Prompt template updated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(prompt.id),
                "name": prompt.name,
                "version": prompt.version,
                "status": prompt.status,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating prompt: {str(e)}")
        return create_response(
            message="Failed to update prompt template",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@prompt_admin_routes.post("/{prompt_id}/activate")
def activate_prompt(
    prompt_id: str,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Activate a prompt version. Archive other active versions with the same name."""
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="activate")

        prompt = session.query(PromptTemplate).filter(
            PromptTemplate.id == prompt_id,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        if not prompt:
            return create_response(
                message="Prompt template not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        # Archive any other active version with the same name
        session.query(PromptTemplate).filter(
            PromptTemplate.name == prompt.name,
            PromptTemplate.status == "active",
            PromptTemplate.id != prompt.id,
            PromptTemplate.is_deleted.is_(False),
        ).update({"status": "archived"}, synchronize_session="fetch")

        prompt.status = "active"
        session.commit()

        return create_response(
            message="Prompt template activated successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(prompt.id),
                "name": prompt.name,
                "version": prompt.version,
                "status": prompt.status,
            },
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error activating prompt: {str(e)}")
        return create_response(
            message="Failed to activate prompt template",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@prompt_admin_routes.get("/{prompt_id}/diff")
def diff_prompt_versions(
    prompt_id: str,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
    user_data: dict = Depends(require_role("super-admin")),
):
    """Compare two versions of a prompt template by name."""
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="diff")

        # Get the prompt to find the name
        prompt = session.query(PromptTemplate).filter(
            PromptTemplate.id == prompt_id,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        if not prompt:
            return create_response(
                message="Prompt template not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        version_1 = session.query(PromptTemplate).filter(
            PromptTemplate.name == prompt.name,
            PromptTemplate.version == v1,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        version_2 = session.query(PromptTemplate).filter(
            PromptTemplate.name == prompt.name,
            PromptTemplate.version == v2,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        if not version_1 or not version_2:
            return create_response(
                message="One or both versions not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        return create_response(
            message="Version comparison retrieved successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "name": prompt.name,
                "v1": {
                    "version": version_1.version,
                    "status": version_1.status,
                    "template_text": version_1.template_text,
                    "variables_json": version_1.variables_json,
                },
                "v2": {
                    "version": version_2.version,
                    "status": version_2.status,
                    "template_text": version_2.template_text,
                    "variables_json": version_2.variables_json,
                },
            },
        )
    except Exception as e:
        logger.error(f"Error diffing prompts: {str(e)}")
        return create_response(
            message="Failed to compare prompt versions",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()


@prompt_admin_routes.post("/{prompt_id}/test")
def test_prompt(
    prompt_id: str,
    variables: Optional[Dict[str, str]] = None,
    user_data: dict = Depends(require_role("super-admin")),
):
    """Test a prompt template by replacing {{var}} placeholders with provided values."""
    session = ScopedSession()
    try:
        log_access(user_data, "prompt_admin", action="test")

        prompt = session.query(PromptTemplate).filter(
            PromptTemplate.id == prompt_id,
            PromptTemplate.is_deleted.is_(False),
        ).first()

        if not prompt:
            return create_response(
                message="Prompt template not found",
                status=False,
                error_code=NOT_FOUND,
                status_code=404,
            )

        rendered = prompt.template_text
        if variables:
            for key, value in variables.items():
                rendered = rendered.replace("{{" + key + "}}", str(value))

        # Find any remaining unresolved placeholders
        unresolved = re.findall(r"\{\{(\w+)\}\}", rendered)

        return create_response(
            message="Prompt template rendered successfully",
            status=True,
            error_code=SUCCESS_CODE,
            data={
                "id": str(prompt.id),
                "name": prompt.name,
                "version": prompt.version,
                "rendered_text": rendered,
                "unresolved_variables": unresolved,
            },
        )
    except Exception as e:
        logger.error(f"Error testing prompt: {str(e)}")
        return create_response(
            message="Failed to test prompt template",
            status=False,
            error_code=SOMETHING_WENT_WRONG,
            status_code=500,
        )
    finally:
        session.close()
        ScopedSession.remove()
