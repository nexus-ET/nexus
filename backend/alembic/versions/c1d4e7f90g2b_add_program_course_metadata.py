"""add program description and course level fields

Revision ID: c1d4e7f90g2b
Revises: b0c3d6e89f1a
Create Date: 2026-07-07 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d4e7f90g2b"
down_revision: Union[str, Sequence[str], None] = "b0c3d6e89f1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "target_programs",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "target_courses",
        sa.Column("level", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("target_courses", "level")
    op.drop_column("target_programs", "description")
