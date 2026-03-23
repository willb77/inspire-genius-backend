"""Phase 6 — query optimization indexes

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-23

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Feedback indexes
    op.create_index(
        "ix_feedback_user_id", "feedback", ["user_id"], if_not_exists=True
    )
    op.create_index(
        "ix_feedback_agent_id", "feedback", ["agent_id"], if_not_exists=True
    )
    op.create_index(
        "ix_feedback_type", "feedback", ["feedback_type"], if_not_exists=True
    )

    # Feedback corrections
    op.create_index(
        "ix_feedback_corrections_status",
        "feedback_corrections",
        ["status"],
        if_not_exists=True,
    )

    # Prompt templates
    op.create_index(
        "ix_prompt_templates_name_version",
        "prompt_templates",
        ["name", "version"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_prompt_templates_status",
        "prompt_templates",
        ["status"],
        if_not_exists=True,
    )

    # Agent memories
    op.create_index(
        "ix_agent_memories_agent",
        "agent_memories",
        ["agent_id"],
        if_not_exists=True,
    )

    # Reports & export jobs
    op.create_index(
        "ix_reports_user_status",
        "reports",
        ["user_id", "status"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_export_jobs_user", "export_jobs", ["user_id"], if_not_exists=True
    )

    # Users email (likely exists, use if_not_exists)
    op.create_index(
        "ix_users_email", "users", ["email"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_export_jobs_user", table_name="export_jobs")
    op.drop_index("ix_reports_user_status", table_name="reports")
    op.drop_index("ix_agent_memories_agent", table_name="agent_memories")
    op.drop_index("ix_prompt_templates_status", table_name="prompt_templates")
    op.drop_index("ix_prompt_templates_name_version", table_name="prompt_templates")
    op.drop_index("ix_feedback_corrections_status", table_name="feedback_corrections")
    op.drop_index("ix_feedback_type", table_name="feedback")
    op.drop_index("ix_feedback_agent_id", table_name="feedback")
    op.drop_index("ix_feedback_user_id", table_name="feedback")
