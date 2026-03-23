# """added organization type and is_onboarded

# Revision ID: b8fdd560004f
# Revises: '3e05feacbbe5'
# Create Date: 2025-11-03 10:15:29.008522

# """

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql # Import for op.create_type/drop_type

# revision identifiers, used by Alembic.
revision: str = 'b8fdd560004f'
down_revision: Union[str, None] = '3e05feacbbe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

organization_type_enum = postgresql.ENUM('BOTH', 'EDUCATION', 'CORPORATE', name='organizationtypeenum')

def upgrade() -> None:
    # --- STEP 1 & 2: Create ENUM and Add Column (Allowing NULL) ---
    # 1. Create the ENUM type
    organization_type_enum.create(op.get_bind(), checkfirst=True)
    
    # 2. Add the 'type' column, but set nullable=True TEMPORARILY
    op.add_column(
        'organization', 
        sa.Column('type', organization_type_enum, nullable=True) # <-- IMPORTANT: Set to True
    )

    # --- STEP 3: Populate Existing Rows with a Default Value ---
    # You must pick one of your ENUM values (e.g., 'BOTH') as a default.
    op.execute("UPDATE organization SET type = 'BOTH' WHERE type IS NULL")

    # --- STEP 4: Change Column to NOT NULL ---
    # This enforces the constraint on the already-populated column.
    op.alter_column('organization', 'type', nullable=False)
    
    # Other additions (optional, but good practice to keep them separate)
    op.add_column('business', sa.Column('is_onboarded', sa.Boolean(), nullable=True))
    op.add_column('organization', sa.Column('is_onboarded', sa.Boolean(), nullable=True))


def downgrade() -> None:
    # When downgrading, drop the column first, then the type.
    op.drop_column('organization', 'is_onboarded')
    op.drop_column('organization', 'type')
    op.drop_column('business', 'is_onboarded')
    organization_type_enum.drop(op.get_bind(), checkfirst=True)
