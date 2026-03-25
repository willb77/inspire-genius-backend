"""Seed multi-role auth roles and add index on roles.name

Revision ID: a1b2c3d4e5f6
Revises: ef0d272b9ff9
Create Date: 2026-03-19

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "076f24d8f587"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Roles to ensure exist
REQUIRED_ROLES = [
    "user",
    "super-admin",
    "coach-admin",
    "org-admin",
    "prompt-engineer",
]


def upgrade() -> None:
    # 1. Add index on roles.name for faster lookups
    op.create_index("ix_roles_name", "roles", ["name"], unique=False)

    # 2. Seed the required roles (skip if already present)
    conn = op.get_bind()
    for role_name in REQUIRED_ROLES:
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


def downgrade() -> None:
    op.drop_index("ix_roles_name", table_name="roles")
