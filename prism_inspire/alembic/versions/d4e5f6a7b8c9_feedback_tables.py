"""feedback tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────
    feedback_type_enum = postgresql.ENUM(
        "correction", "rating", "thumbs_up", "thumbs_down", "comment",
        name="feedback_type_enum", create_type=True,
    )
    export_format_enum = postgresql.ENUM(
        "jsonl", "csv", "parquet",
        name="export_format_enum", create_type=True,
    )
    export_status_enum = postgresql.ENUM(
        "pending", "processing", "completed", "failed",
        name="export_status_enum", create_type=True,
    )
    feedback_type_enum.create(op.get_bind(), checkfirst=True)
    export_format_enum.create(op.get_bind(), checkfirst=True)
    export_status_enum.create(op.get_bind(), checkfirst=True)

    # ── feedback ──────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("original_response", sa.Text(), nullable=False),
        sa.Column("correction", sa.Text(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("feedback_type", feedback_type_enum, nullable=False, server_default="rating"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_session_id", "feedback", ["session_id"])
    op.create_index("ix_feedback_user_created", "feedback", ["user_id", "created_at"])
    op.create_index("ix_feedback_agent_rating", "feedback", ["agent_id", "rating"])
    op.create_index("ix_feedback_created_at", "feedback", ["created_at"])
    op.create_index("ix_feedback_type", "feedback", ["feedback_type"])

    # ── feedback_corrections ──────────────────────────────────────
    op.create_table(
        "feedback_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "feedback_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feedback.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feedback_corrections_feedback_id", "feedback_corrections", ["feedback_id"])

    # ── training_exports ──────────────────────────────────────────
    op.create_table(
        "training_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("export_format", export_format_enum, nullable=False, server_default="jsonl"),
        sa.Column("filters", postgresql.JSONB(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("file_url", sa.String(1024), nullable=True),
        sa.Column("status", export_status_enum, nullable=False, server_default="pending"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_training_exports_status", "training_exports", ["status"])
    op.create_index("ix_training_exports_created_by", "training_exports", ["created_by"])


def downgrade() -> None:
    op.drop_table("training_exports")
    op.drop_table("feedback_corrections")
    op.drop_table("feedback")

    op.execute("DROP TYPE IF EXISTS export_status_enum")
    op.execute("DROP TYPE IF EXISTS export_format_enum")
    op.execute("DROP TYPE IF EXISTS feedback_type_enum")
