"""Phase 3 — role-specific tables + goals, activity, costs, org tree

Revision ID: c3d4e5f6a7b8
Revises: ef0d272b9ff9
Create Date: 2026-03-21

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ROLES = ["manager", "company-admin", "practitioner", "distributor"]


def upgrade() -> None:
    # ── Seed new roles ──
    conn = op.get_bind()
    for role_name in NEW_ROLES:
        existing = conn.execute(
            sa.text("SELECT id FROM roles WHERE LOWER(name) = :name"),
            {"name": role_name.lower()},
        ).fetchone()
        if not existing:
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, name, role_level, is_deleted, created_at) "
                    "VALUES (:id, :name, 'SYSTEM', false, NOW())"
                ),
                {"id": str(uuid.uuid4()), "name": role_name},
            )

    # Add index on roles.name if not present
    try:
        op.create_index("ix_roles_name", "roles", ["name"], unique=False)
    except Exception:
        pass  # index may already exist

    # ── Manager tables ──
    op.create_table(
        "training_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("due_date", sa.Date),
        sa.Column("status", sa.String(20), nullable=False, server_default="assigned"),
        sa.Column("progress_pct", sa.Integer, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "hiring_positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organization.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("position_id", UUID(as_uuid=True), sa.ForeignKey("hiring_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("email", sa.String(150)),
        sa.Column("phone", sa.String(30)),
        sa.Column("resume_url", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="applied"),
        sa.Column("prism_score", sa.Float),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "interviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", UUID(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interviewer_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, server_default="30"),
        sa.Column("location", sa.String(200)),
        sa.Column("meeting_url", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text),
        sa.Column("rating", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )

    # ── Practitioner tables ──
    op.create_table(
        "practitioner_clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("prism_score", sa.Float),
        sa.Column("session_count", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("notes", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "coaching_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("practitioner_client_id", UUID(as_uuid=True), sa.ForeignKey("practitioner_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, server_default="60"),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("session_type", sa.String(50), server_default="one_on_one"),
        sa.Column("notes", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("rating", sa.Integer),
        sa.Column("credits_used", sa.Numeric(10, 2), server_default="1"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "practitioner_credits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False, unique=True),
        sa.Column("total_credits", sa.Numeric(10, 2), server_default="0"),
        sa.Column("used_credits", sa.Numeric(10, 2), server_default="0"),
        sa.Column("reserved_credits", sa.Numeric(10, 2), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "follow_ups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("due_date", sa.Date, nullable=False),
        sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )

    # ── Distributor tables ──
    op.create_table(
        "distributor_territories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("distributor_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("country", sa.String(100)),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "distributor_practitioners",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("distributor_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "distributor_credits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("distributor_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False, unique=True),
        sa.Column("total_purchased", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total_allocated", sa.Numeric(10, 2), server_default="0"),
        sa.Column("total_used", sa.Numeric(10, 2), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("distributor_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("practitioner_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("transaction_type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("reference_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Phase 3 shared tables ──
    op.create_table(
        "user_goals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("due_date", sa.Date),
        sa.Column("progress_pct", sa.Integer, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )
    op.create_table(
        "user_activities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("activity_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("metadata_json", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "cost_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organization.id")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("period_start", sa.Date),
        sa.Column("period_end", sa.Date),
        sa.Column("description", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "org_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organization.id"), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("org_nodes.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("node_type", sa.String(50), server_default="department"),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id")),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("is_deleted", sa.Boolean, server_default="false"),
    )

    # ── Indexes ──
    op.create_index("ix_training_assignments_manager", "training_assignments", ["manager_id"])
    op.create_index("ix_training_assignments_user", "training_assignments", ["user_id"])
    op.create_index("ix_hiring_positions_manager", "hiring_positions", ["manager_id"])
    op.create_index("ix_candidates_position", "candidates", ["position_id"])
    op.create_index("ix_interviews_interviewer", "interviews", ["interviewer_id"])
    op.create_index("ix_interviews_scheduled", "interviews", ["scheduled_at"])
    op.create_index("ix_practitioner_clients_pract", "practitioner_clients", ["practitioner_id"])
    op.create_index("ix_coaching_sessions_pract", "coaching_sessions", ["practitioner_id"])
    op.create_index("ix_coaching_sessions_scheduled", "coaching_sessions", ["scheduled_at"])
    op.create_index("ix_follow_ups_pract", "follow_ups", ["practitioner_id"])
    op.create_index("ix_follow_ups_due", "follow_ups", ["due_date"])
    op.create_index("ix_dist_practitioners_dist", "distributor_practitioners", ["distributor_id"])
    op.create_index("ix_credit_txn_dist", "credit_transactions", ["distributor_id"])
    op.create_index("ix_user_goals_user", "user_goals", ["user_id"])
    op.create_index("ix_user_activities_user_date", "user_activities", ["user_id", "created_at"])
    op.create_index("ix_cost_records_scope_org", "cost_records", ["scope", "organization_id"])
    op.create_index("ix_org_nodes_org", "org_nodes", ["organization_id"])
    op.create_index("ix_org_nodes_parent", "org_nodes", ["parent_id"])


def downgrade() -> None:
    tables = [
        "org_nodes", "cost_records", "user_activities", "user_goals",
        "credit_transactions", "distributor_credits",
        "distributor_practitioners", "distributor_territories",
        "follow_ups", "practitioner_credits",
        "coaching_sessions", "practitioner_clients",
        "interviews", "candidates",
        "hiring_positions", "training_assignments",
    ]
    for t in tables:
        op.drop_table(t)
