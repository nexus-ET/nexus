"""Link full_time_study_years to levels.

Revision ID: i0b3c6ftlevels
Revises: h9a2b5studyyears
Create Date: 2026-07-27 07:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i0b3c6ftlevels"
down_revision: Union[str, Sequence[str], None] = "h9a2b5studyyears"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# FT code → levels.code
FT_LEVEL_MAP: dict[str, str] = {
    "12": "FOUNDATIONAL",
    "13": "FOUNDATIONAL",
    "14": "UNDERGRAD",
    "15": "UNDERGRAD",
    "16": "UNDERGRAD",
    "17+": "GRADUATE",
}


def upgrade() -> None:
    op.add_column(
        "full_time_study_years",
        sa.Column("level_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_full_time_study_years_level_id",
        "full_time_study_years",
        ["level_id"],
    )
    op.create_foreign_key(
        "fk_full_time_study_years_level_id",
        "full_time_study_years",
        "levels",
        ["level_id"],
        ["id"],
    )

    conn = op.get_bind()
    level_rows = conn.execute(sa.text("SELECT id, code FROM levels")).fetchall()
    level_by_code = {str(code).upper(): int(level_id) for level_id, code in level_rows}

    for ft_code, level_code in FT_LEVEL_MAP.items():
        level_id = level_by_code.get(level_code)
        if level_id is None:
            continue
        conn.execute(
            sa.text(
                "UPDATE full_time_study_years "
                "SET level_id = :level_id "
                "WHERE code = :code"
            ),
            {"level_id": level_id, "code": ft_code},
        )

    op.alter_column("full_time_study_years", "level_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint(
        "fk_full_time_study_years_level_id",
        "full_time_study_years",
        type_="foreignkey",
    )
    op.drop_index("ix_full_time_study_years_level_id", table_name="full_time_study_years")
    op.drop_column("full_time_study_years", "level_id")
