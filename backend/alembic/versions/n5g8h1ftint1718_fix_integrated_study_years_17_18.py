"""Fix Integrated Degree FT study years to 17+ and 18+.

Revision ID: n5g8h1ftint1718
Revises: m4f7g0ft16int
Create Date: 2026-07-27 19:35:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n5g8h1ftint1718"
down_revision: Union[str, Sequence[str], None] = "m4f7g0ft16int"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INTEGRATED_ROWS: list[tuple[str, str, int]] = [
    ("17+", "17+ - Master's / Postgraduate", 7),
    ("18+", "18+ - Doctoral / Research", 8),
]


def _level_id(conn, code: str, fallback: int) -> int:
    row = conn.execute(
        sa.text("SELECT id FROM levels WHERE code = :code LIMIT 1"),
        {"code": code},
    ).fetchone()
    return int(row[0]) if row else fallback


def upgrade() -> None:
    conn = op.get_bind()
    integrated_id = _level_id(conn, "INTEGRATED", 5)
    undergrad_id = _level_id(conn, "UNDERGRAD", 2)

    # Remove incorrect Integrated mappings for 12/13.
    conn.execute(
        sa.text(
            "DELETE FROM full_time_study_years "
            "WHERE level_id = :level_id AND code IN ('12', '13')"
        ),
        {"level_id": integrated_id},
    )

    # Restore 16 to Undergraduate (no longer Integrated-only).
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET level_id = :level_id, sort_order = 6 "
            "WHERE code = '16'"
        ),
        {"level_id": undergrad_id},
    )

    for code, label, sort_order in INTEGRATED_ROWS:
        existing = conn.execute(
            sa.text(
                "SELECT id FROM full_time_study_years "
                "WHERE code = :code AND level_id = :level_id"
            ),
            {"code": code, "level_id": integrated_id},
        ).fetchone()
        if existing is None:
            conn.execute(
                sa.text(
                    "INSERT INTO full_time_study_years "
                    "(code, label, level_id, is_active, sort_order) "
                    "VALUES (:code, :label, :level_id, true, :sort_order)"
                ),
                {
                    "code": code,
                    "label": label,
                    "level_id": integrated_id,
                    "sort_order": sort_order,
                },
            )
        else:
            conn.execute(
                sa.text(
                    "UPDATE full_time_study_years "
                    "SET label = :label, is_active = true, sort_order = :sort_order "
                    "WHERE code = :code AND level_id = :level_id"
                ),
                {
                    "code": code,
                    "label": label,
                    "level_id": integrated_id,
                    "sort_order": sort_order,
                },
            )


def downgrade() -> None:
    conn = op.get_bind()
    integrated_id = _level_id(conn, "INTEGRATED", 5)

    conn.execute(
        sa.text(
            "DELETE FROM full_time_study_years "
            "WHERE level_id = :level_id AND code IN ('17+', '18+')"
        ),
        {"level_id": integrated_id},
    )

    # Restore prior incorrect Integrated 12/13 + 16 mapping.
    for code, label, sort_order in (
        ("12", "12 - High School", 2),
        ("13", "13 - Foundation Year", 3),
    ):
        conn.execute(
            sa.text(
                "INSERT INTO full_time_study_years "
                "(code, label, level_id, is_active, sort_order) "
                "VALUES (:code, :label, :level_id, true, :sort_order)"
            ),
            {
                "code": code,
                "label": label,
                "level_id": integrated_id,
                "sort_order": sort_order,
            },
        )
    conn.execute(
        sa.text(
            "UPDATE full_time_study_years "
            "SET level_id = :level_id "
            "WHERE code = '16'"
        ),
        {"level_id": integrated_id},
    )
