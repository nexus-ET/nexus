"""Allow same FT study year codes per level; add Integrated 12/13.

Revision ID: l3e6f9ftint1213
Revises: k2d5e8ftcode10
Create Date: 2026-07-27 19:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l3e6f9ftint1213"
down_revision: Union[str, Sequence[str], None] = "k2d5e8ftcode10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INTEGRATED_ROWS: list[tuple[str, str, int]] = [
    ("12", "12 - High School", 2),
    ("13", "13 - Foundation Year", 3),
]


def upgrade() -> None:
    # Same study-year code may exist under multiple levels (e.g. 12/13).
    op.drop_index("ix_full_time_study_years_code", table_name="full_time_study_years")
    op.create_index(
        "ix_full_time_study_years_code",
        "full_time_study_years",
        ["code"],
        unique=False,
    )
    op.create_index(
        "uq_full_time_study_years_code_level_id",
        "full_time_study_years",
        ["code", "level_id"],
        unique=True,
    )

    conn = op.get_bind()
    level_row = conn.execute(
        sa.text("SELECT id FROM levels WHERE code = 'INTEGRATED' LIMIT 1")
    ).fetchone()
    if level_row is None:
        # Fallback to known id used in local/staging seeds.
        integrated_id = 5
        exists = conn.execute(
            sa.text("SELECT id FROM levels WHERE id = :id"),
            {"id": integrated_id},
        ).fetchone()
        if exists is None:
            raise RuntimeError("Integrated Degree level (INTEGRATED / id=5) is required.")
    else:
        integrated_id = int(level_row[0])

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
    level_row = conn.execute(
        sa.text("SELECT id FROM levels WHERE code = 'INTEGRATED' LIMIT 1")
    ).fetchone()
    integrated_id = int(level_row[0]) if level_row else 5

    conn.execute(
        sa.text(
            "DELETE FROM full_time_study_years "
            "WHERE level_id = :level_id AND code IN ('12', '13')"
        ),
        {"level_id": integrated_id},
    )

    op.drop_index(
        "uq_full_time_study_years_code_level_id",
        table_name="full_time_study_years",
    )
    op.drop_index("ix_full_time_study_years_code", table_name="full_time_study_years")
    op.create_index(
        "ix_full_time_study_years_code",
        "full_time_study_years",
        ["code"],
        unique=True,
    )
