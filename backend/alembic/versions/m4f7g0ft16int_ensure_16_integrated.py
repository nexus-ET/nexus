"""Ensure study year 16 maps to Integrated Degree.

Revision ID: m4f7g0ft16int
Revises: l3e6f9ftint1213
Create Date: 2026-07-27 19:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m4f7g0ft16int"
down_revision: Union[str, Sequence[str], None] = "l3e6f9ftint1213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    level_row = conn.execute(
        sa.text("SELECT id FROM levels WHERE code = 'INTEGRATED' LIMIT 1")
    ).fetchone()
    integrated_id = int(level_row[0]) if level_row else 5
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET level_id = :level_id "
            "WHERE code = '16'"
        ),
        {"level_id": integrated_id},
    )


def downgrade() -> None:
    conn = op.get_bind()
    level_row = conn.execute(
        sa.text("SELECT id FROM levels WHERE code = 'UNDERGRAD' LIMIT 1")
    ).fetchone()
    undergrad_id = int(level_row[0]) if level_row else 2
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET level_id = :level_id "
            "WHERE code = '16'"
        ),
        {"level_id": undergrad_id},
    )
