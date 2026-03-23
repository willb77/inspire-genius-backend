"""Phase 4 — feedback, corrections, prompt templates, agent memories

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-22

"""
from __future__ import annotations

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- feedback --
    op.create_table(
        "feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("response_id", sa.String(100), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("feedback_type", sa.String(20), nullable=False),
        sa.Column("correction_text", sa.Text, nullable=True),
        sa.Column("rating", sa.Integer, nullable=True),
        sa.Column("context_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false")),
    )
    op.create_index("ix_feedback_user_id", "feedback", ["user_id"])
    op.create_index("ix_feedback_agent_id", "feedback", ["agent_id"])
    op.create_index("ix_feedback_type", "feedback", ["feedback_type"])
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"])

    # -- feedback_corrections --
    op.create_table(
        "feedback_corrections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("feedback_id", UUID(as_uuid=True), sa.ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_response", sa.Text, nullable=True),
        sa.Column("corrected_response", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'")),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight", sa.Float, server_default=sa.text("1.0")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_feedback_corrections_feedback_id", "feedback_corrections", ["feedback_id"])
    op.create_index("ix_feedback_corrections_status", "feedback_corrections", ["status"])

    # -- prompt_templates --
    op.create_table(
        "prompt_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_text", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(20), server_default=sa.text("'draft'")),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variables_json", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false")),
        sa.UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
    )
    op.create_index("ix_prompt_templates_agent_id", "prompt_templates", ["agent_id"])
    op.create_index("ix_prompt_templates_status", "prompt_templates", ["status"])

    # -- agent_memories --
    op.create_table(
        "agent_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=True),
        sa.Column("weight", sa.Float, server_default=sa.text("1.0")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_agent_memories_agent_id", "agent_memories", ["agent_id"])
    op.create_index("ix_agent_memories_memory_type", "agent_memories", ["memory_type"])
    op.create_index("ix_agent_memories_is_active", "agent_memories", ["is_active"])


def downgrade() -> None:
    op.drop_table("agent_memories")
    op.drop_table("prompt_templates")
    op.drop_table("feedback_corrections")
    op.drop_table("feedback")
