"""Add full_time_study_years lookup and education column.

Revision ID: h9a2b5studyyears
Revises: g8z1a4timestamptz
Create Date: 2026-07-27 07:00:00.000000

Idempotent: safe when the table/column already exist (e.g. staging schema
copied from develop while alembic_version lagged).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h9a2b5studyyears"
down_revision: Union[str, Sequence[str], None] = "g8z1a4timestamptz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_ROWS: list[tuple[str, str, int]] = [
    ("12", "12 - High School", 1),
    ("13", "13 - Foundation Year", 2),
    ("14", "14 - Associate / Diploma", 3),
    ("15", "15 - 3-Year Bachelor's", 4),
    ("16", "16 - 4-Year Bachelor's", 5),
    ("17+", "17+ - Master's / Postgraduate", 6),
]

# Same mapping as i0b3c6ftlevels — needed when staging already has NOT NULL level_id.
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


def _seed_missing_rows() -> None:
    conn = op.get_bind()
    cols = {c["name"] for c in _inspector().get_columns("full_time_study_years")}
    has_level_id = "level_id" in cols

    level_by_code: dict[str, int] = {}
    if has_level_id and _inspector().has_table("levels"):
        level_rows = conn.execute(sa.text("SELECT id, code FROM levels")).fetchall()
        level_by_code = {str(code).upper(): int(level_id) for level_id, code in level_rows}

    for code, label, sort_order in SEED_ROWS:
        exists = conn.execute(
            sa.text("SELECT 1 FROM full_time_study_years WHERE code = :code LIMIT 1"),
            {"code": code},
        ).scalar()
        if exists:
            continue

        params = {"code": code, "label": label, "sort_order": sort_order}
        if has_level_id:
            level_code = FT_LEVEL_MAP.get(code)
            level_id = level_by_code.get(level_code) if level_code else None
            if level_id is None:
                # Cannot satisfy NOT NULL level_id yet — leave for later catalog migrations.
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO full_time_study_years "
                    "(code, label, is_active, sort_order, level_id) "
                    "VALUES (:code, :label, true, :sort_order, :level_id)"
                ),
                {**params, "level_id": level_id},
            )
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO full_time_study_years (code, label, is_active, sort_order) "
                    "VALUES (:code, :label, true, :sort_order)"
                ),
                params,
            )


def upgrade() -> None:
    inspector = _inspector()
    if not inspector.has_table("full_time_study_years"):
        op.create_table(
            "full_time_study_years",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=10), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    inspector = _inspector()
    indexes = {idx["name"] for idx in inspector.get_indexes("full_time_study_years")}
    if "ix_full_time_study_years_id" not in indexes:
        op.create_index("ix_full_time_study_years_id", "full_time_study_years", ["id"])
    if "ix_full_time_study_years_code" not in indexes:
        op.create_index(
            "ix_full_time_study_years_code",
            "full_time_study_years",
            ["code"],
            unique=True,
        )

    _seed_missing_rows()

    if inspector.has_table("candidate_educations"):
        edu_cols = {c["name"] for c in inspector.get_columns("candidate_educations")}
        if "full_time_study_years" not in edu_cols:
            op.add_column(
                "candidate_educations",
                sa.Column("full_time_study_years", sa.String(length=10), nullable=True),
            )


def downgrade() -> None:
    inspector = _inspector()
    if inspector.has_table("candidate_educations"):
        edu_cols = {c["name"] for c in inspector.get_columns("candidate_educations")}
        if "full_time_study_years" in edu_cols:
            op.drop_column("candidate_educations", "full_time_study_years")
    if inspector.has_table("full_time_study_years"):
        indexes = {idx["name"] for idx in inspector.get_indexes("full_time_study_years")}
        if "ix_full_time_study_years_code" in indexes:
            op.drop_index("ix_full_time_study_years_code", table_name="full_time_study_years")
        if "ix_full_time_study_years_id" in indexes:
            op.drop_index("ix_full_time_study_years_id", table_name="full_time_study_years")
        op.drop_table("full_time_study_years")
