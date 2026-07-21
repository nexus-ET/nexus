"""Add is_active flag to levels table.

Revision ID: w1x4y20z1a2b
Revises: v0w3x19y0z1a
Create Date: 2026-07-09 23:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "w1x4y20z1a2b"
down_revision: Union[str, Sequence[str], None] = "v0w3x19y0z1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "levels",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("levels", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("levels", "is_active")
