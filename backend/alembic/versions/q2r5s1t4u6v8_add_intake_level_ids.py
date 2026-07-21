"""Add level selections to institution intakes.

Revision ID: q2r5s1t4u6v8
Revises: p1q4r0s3t5u7
Create Date: 2026-07-15 12:06:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "q2r5s1t4u6v8"
down_revision: Union[str, Sequence[str], None] = "p1q4r0s3t5u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institution_intakes",
        sa.Column(
            "level_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("institution_intakes", "level_ids")
