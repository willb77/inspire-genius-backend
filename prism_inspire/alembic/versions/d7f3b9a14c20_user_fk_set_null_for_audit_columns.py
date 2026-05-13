"""user_fk_set_null_for_audit_columns

Make the two unconstrained FKs to users.user_id deferral-safe so the
super-admin force-purge path can hard-delete soft-deleted users without
tripping IntegrityError.

- issues.reported_by: was NOT NULL + NO ACTION on delete. Now nullable + SET NULL.
- organization_agents.assigned_by: already nullable, but NO ACTION on delete. Now SET NULL.

Revision ID: d7f3b9a14c20
Revises: f6a7b8c9d0e1
Create Date: 2026-05-13

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d7f3b9a14c20"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # issues.reported_by: NOT NULL -> NULL, then re-create FK with SET NULL
    op.alter_column(
        "issues",
        "reported_by",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.drop_constraint("fk_issues_reported_by_users", "issues", type_="foreignkey")
    op.create_foreign_key(
        "fk_issues_reported_by_users",
        "issues",
        "users",
        ["reported_by"],
        ["user_id"],
        ondelete="SET NULL",
    )

    # organization_agents.assigned_by: already nullable, just re-create FK with SET NULL
    op.drop_constraint(
        "fk_organization_agents_assigned_by_users",
        "organization_agents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_organization_agents_assigned_by_users",
        "organization_agents",
        "users",
        ["assigned_by"],
        ["user_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Restore organization_agents.assigned_by FK without ON DELETE clause.
    op.drop_constraint(
        "fk_organization_agents_assigned_by_users",
        "organization_agents",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_organization_agents_assigned_by_users",
        "organization_agents",
        "users",
        ["assigned_by"],
        ["user_id"],
    )

    # Restore issues.reported_by FK without ON DELETE clause and re-impose NOT NULL.
    # WARNING: downgrade will fail if any issues.reported_by IS NULL — those rows
    # must be cleaned up first, or the downgrade aborted.
    op.drop_constraint("fk_issues_reported_by_users", "issues", type_="foreignkey")
    op.create_foreign_key(
        "fk_issues_reported_by_users",
        "issues",
        "users",
        ["reported_by"],
        ["user_id"],
    )
    op.alter_column(
        "issues",
        "reported_by",
        existing_type=sa.UUID(),
        nullable=False,
    )
