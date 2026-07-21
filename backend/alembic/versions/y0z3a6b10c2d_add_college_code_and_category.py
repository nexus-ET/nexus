"""Add college code and category columns.

Revision ID: y0z3a6b10c2d
Revises: x9y2z5a09b1c
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "y0z3a6b10c2d"
down_revision = "x9y2z5a09b1c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("colleges", sa.Column("code", sa.String(length=50), nullable=True))
    op.add_column("colleges", sa.Column("category", sa.String(length=64), nullable=True))
    op.execute(
        """
        UPDATE colleges
        SET category = 'College'
        WHERE category IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("colleges", "category")
    op.drop_column("colleges", "code")
