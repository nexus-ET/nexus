"""Make course major optional for direct program ownership.

Revision ID: m8n1o7p0q2r4
Revises: l7m0n6o9p1q3
Create Date: 2026-07-13 21:42:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "m8n1o7p0q2r4"
down_revision: Union[str, Sequence[str], None] = "l7m0n6o9p1q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "education_courses",
        "education_major_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM education_courses WHERE education_major_id IS NULL"
    )
    op.alter_column(
        "education_courses",
        "education_major_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
