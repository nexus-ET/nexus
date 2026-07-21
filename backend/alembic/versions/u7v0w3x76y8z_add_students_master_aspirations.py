"""add students_master aspirations_data column

Revision ID: u7v0w3x76y8z
Revises: t6u9v2w65x7y
Create Date: 2026-07-06 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "u7v0w3x76y8z"
down_revision: Union[str, Sequence[str], None] = "t6u9v2w65x7y"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "students_master",
        sa.Column(
            "aspirations_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("students_master", "aspirations_data")
