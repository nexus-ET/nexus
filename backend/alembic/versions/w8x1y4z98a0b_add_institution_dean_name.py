"""Add dean_name to institutions.

Revision ID: w8x1y4z98a0b
Revises: v7w0x3y87z9a
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "w8x1y4z98a0b"
down_revision = "v7w0x3y87z9a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutions", sa.Column("dean_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("institutions", "dean_name")
