"""add students_master gender and marital_status columns

Revision ID: v8w1x4y87z9a
Revises: u7v0w3x76y8z
Create Date: 2026-07-06 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v8w1x4y87z9a"
down_revision: Union[str, Sequence[str], None] = "u7v0w3x76y8z"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("students_master", sa.Column("gender", sa.String(length=20), nullable=True))
    op.add_column(
        "students_master",
        sa.Column("marital_status", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("students_master", "marital_status")
    op.drop_column("students_master", "gender")
