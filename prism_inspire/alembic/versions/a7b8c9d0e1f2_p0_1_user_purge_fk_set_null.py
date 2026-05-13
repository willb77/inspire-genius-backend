"""P0-1: relax user FKs to ON DELETE SET NULL for purge-inactive flow

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-13

The Purge Inactive Users flow hard-deletes rows from `public.users` for
super-admin housekeeping. Two FK columns currently use the implicit
NO ACTION rule and will trip when a soft-deleted user has historical
references:

  - issues.reported_by         -> users.user_id   (NOT NULL, NO ACTION)
  - organization_agents.assigned_by -> users.user_id (NULL, NO ACTION)

This migration:
  1. Makes `issues.reported_by` nullable so SET NULL can land safely.
  2. Re-creates both FKs with ondelete='SET NULL'.

Downgrade reverses the FK rule and restores NOT NULL on issues.reported_by
(values that became NULL during the upgrade window will block downgrade —
caller must reconcile manually).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- issues.reported_by ----
    # Allow NULL so ON DELETE SET NULL is valid.
    op.alter_column(
        "issues",
        "reported_by",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.drop_constraint(
        "fk_issues_reported_by_users",
        "issues",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_issues_reported_by_users",
        "issues",
        "users",
        ["reported_by"],
        ["user_id"],
        ondelete="SET NULL",
    )

    # ---- organization_agents.assigned_by ----
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
    # ---- organization_agents.assigned_by ----
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

    # ---- issues.reported_by ----
    op.drop_constraint(
        "fk_issues_reported_by_users",
        "issues",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_issues_reported_by_users",
        "issues",
        "users",
        ["reported_by"],
        ["user_id"],
    )
    # NOTE: downgrade does NOT restore NOT NULL on issues.reported_by because
    # any rows that lost their reporter via ON DELETE SET NULL would block
    # the alter_column. Operators must reconcile such rows manually if a
    # strict downgrade is required.
