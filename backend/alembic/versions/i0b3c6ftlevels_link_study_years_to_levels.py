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


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if not inspector.has_table("full_time_study_years"):
        return

    cols = {c["name"] for c in inspector.get_columns("full_time_study_years")}
    if "level_id" not in cols:
        op.add_column(
            "full_time_study_years",
            sa.Column("level_id", sa.Integer(), nullable=True),
        )

    inspector = _inspector()
    indexes = {idx["name"] for idx in inspector.get_indexes("full_time_study_years")}
    if "ix_full_time_study_years_level_id" not in indexes:
        op.create_index(
            "ix_full_time_study_years_level_id",
            "full_time_study_years",
            ["level_id"],
        )

    fks = {fk["name"] for fk in inspector.get_foreign_keys("full_time_study_years")}
    if "fk_full_time_study_years_level_id" not in fks:
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
                "WHERE code = :code AND (level_id IS NULL OR level_id IS DISTINCT FROM :level_id)"
            ),
            {"level_id": level_id, "code": ft_code},
        )

    # Only enforce NOT NULL when every row has a level (partial catalogs stay nullable).
    nulls = conn.execute(
        sa.text("SELECT COUNT(*) FROM full_time_study_years WHERE level_id IS NULL")
    ).scalar()
    if not nulls:
        op.alter_column("full_time_study_years", "level_id", nullable=False)


def downgrade() -> None:
    inspector = _inspector()
    if not inspector.has_table("full_time_study_years"):
        return
    fks = {fk["name"] for fk in inspector.get_foreign_keys("full_time_study_years")}
    if "fk_full_time_study_years_level_id" in fks:
        op.drop_constraint(
            "fk_full_time_study_years_level_id",
            "full_time_study_years",
            type_="foreignkey",
        )
    indexes = {idx["name"] for idx in inspector.get_indexes("full_time_study_years")}
    if "ix_full_time_study_years_level_id" in indexes:
        op.drop_index("ix_full_time_study_years_level_id", table_name="full_time_study_years")
    cols = {c["name"] for c in inspector.get_columns("full_time_study_years")}
    if "level_id" in cols:
        op.drop_column("full_time_study_years", "level_id")
