"""Map Integrated Degree and Doctoral to full_time_study_years.

Revision ID: j1c4d7ftdocint
Revises: i0b3c6ftlevels
Create Date: 2026-07-27 07:55:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1c4d7ftdocint"
down_revision: Union[str, Sequence[str], None] = "i0b3c6ftlevels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    level_rows = conn.execute(sa.text("SELECT id, code FROM levels")).fetchall()
    level_by_code = {str(code).upper(): int(level_id) for level_id, code in level_rows}

    integrated_id = level_by_code.get("INTEGRATED")
    doctoral_id = level_by_code.get("DOCTORAL")
    undergrad_id = level_by_code.get("UNDERGRAD")

    if integrated_id is None or doctoral_id is None:
        raise RuntimeError(
            "Levels INTEGRATED and DOCTORAL must exist before mapping full_time_study_years."
        )

    # 16 (4-Year Bachelor's) → Integrated Degree
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET level_id = :level_id "
            "WHERE code = '16'"
        ),
        {"level_id": integrated_id},
    )

    # Add Doctoral FT option when missing
    existing = conn.execute(
        sa.text("SELECT id FROM full_time_study_years WHERE code = '18+'")
    ).fetchone()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO full_time_study_years (code, label, level_id, is_active, sort_order) "
                "VALUES ('18+', '18+ - Doctoral / Research', :level_id, true, 7)"
            ),
            {"level_id": doctoral_id},
        )
    else:
        conn.execute(
            sa.text(
                "UPDATE full_time_study_years "
                "SET label = '18+ - Doctoral / Research', "
                "    level_id = :level_id, "
                "    is_active = true, "
                "    sort_order = 7 "
                "WHERE code = '18+'"
            ),
            {"level_id": doctoral_id},
        )

    # Keep undergrad mapping sanity for 14/15 if somehow unset
    if undergrad_id is not None:
        conn.execute(
            sa.text(
                "UPDATE full_time_study_years "
                "SET level_id = :level_id "
                "WHERE code IN ('14', '15') AND level_id IS DISTINCT FROM :level_id"
            ),
            {"level_id": undergrad_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    level_rows = conn.execute(sa.text("SELECT id, code FROM levels")).fetchall()
    level_by_code = {str(code).upper(): int(level_id) for level_id, code in level_rows}
    undergrad_id = level_by_code.get("UNDERGRAD")

    if undergrad_id is not None:
        conn.execute(
            sa.text(
                "UPDATE full_time_study_years "
                "SET level_id = :level_id "
                "WHERE code = '16'"
            ),
            {"level_id": undergrad_id},
        )

    conn.execute(sa.text("DELETE FROM full_time_study_years WHERE code = '18+'"))
