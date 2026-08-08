"""Add full_time_study_years code 10 (High School).

Revision ID: k2d5e8ftcode10
Revises: j1c4d7ftdocint
Create Date: 2026-07-27 19:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k2d5e8ftcode10"
down_revision: Union[str, Sequence[str], None] = "j1c4d7ftdocint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Make room at sort_order 1 for the new row.
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET sort_order = sort_order + 1 "
            "WHERE sort_order >= 1"
        )
    )

    existing = conn.execute(
        sa.text("SELECT id FROM full_time_study_years WHERE code = '10'")
    ).fetchone()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO full_time_study_years "
                "(code, label, level_id, is_active, sort_order) "
                "VALUES ('10', '10 - High School', 1, true, 1)"
            )
        )
    else:
        conn.execute(
            sa.text(
                "UPDATE full_time_study_years "
                "SET label = '10 - High School', "
                "    level_id = 1, "
                "    is_active = true, "
                "    sort_order = 1 "
                "WHERE code = '10'"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM full_time_study_years WHERE code = '10'"))
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET sort_order = sort_order - 1 "
            "WHERE sort_order > 1"
        )
    )
