"""Add descriptions to majors and courses.

Revision ID: o0p3q9r2s4t6
Revises: n9o2p8q1r3s5
Create Date: 2026-07-15 07:35:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "o0p3q9r2s4t6"
down_revision: Union[str, Sequence[str], None] = "n9o2p8q1r3s5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("education_majors", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("education_courses", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("education_courses", "description")
    op.drop_column("education_majors", "description")
