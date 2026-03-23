"""add_issue_attachments_table

Revision ID: cf3816b156f8
Revises: '00c9f1e79d6c'
Create Date: 2025-10-19 11:24:36.615003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'cf3816b156f8'
down_revision: Union[str, None] = '00c9f1e79d6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create issue_attachments table
    op.create_table(
        'issue_attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('issue_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_key', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('file_size', sa.String(length=20), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['issue_id'], ['issues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.user_id'], ondelete='CASCADE')
    )

    # Create indexes for better query performance
    op.create_index('ix_issue_attachments_issue_id', 'issue_attachments', ['issue_id'])
    op.create_index('ix_issue_attachments_uploaded_by', 'issue_attachments', ['uploaded_by'])
    op.create_index('ix_issue_attachments_is_deleted', 'issue_attachments', ['is_deleted'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_issue_attachments_is_deleted', table_name='issue_attachments')
    op.drop_index('ix_issue_attachments_uploaded_by', table_name='issue_attachments')
    op.drop_index('ix_issue_attachments_issue_id', table_name='issue_attachments')

    # Drop table
    op.drop_table('issue_attachments')
