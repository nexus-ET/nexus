"""add superuser columns to users

Revision ID: 2e1d49fcdf8c
Revises: 02fee3037fcb
Create Date: 2026-05-29 20:14:15.032499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2e1d49fcdf8c'
down_revision: Union[str, Sequence[str], None] = '02fee3037fcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('is_superuser', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('role', sa.String(), server_default='user', nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
    op.drop_column('users', 'is_superuser')
