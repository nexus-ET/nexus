"""Add full_time_study_years lookup and education column.

Revision ID: h9a2b5studyyears
Revises: g8z1a4timestamptz
Create Date: 2026-07-27 07:00:00.000000

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


def upgrade() -> None:
    op.create_table(
        "full_time_study_years",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_full_time_study_years_id", "full_time_study_years", ["id"])
    op.create_index(
        "ix_full_time_study_years_code",
        "full_time_study_years",
        ["code"],
        unique=True,
    )

    study_years = sa.table(
        "full_time_study_years",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        study_years,
        [
            {
                "code": code,
                "label": label,
                "is_active": True,
                "sort_order": sort_order,
            }
            for code, label, sort_order in SEED_ROWS
        ],
    )

    op.add_column(
        "candidate_educations",
        sa.Column("full_time_study_years", sa.String(length=10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_educations", "full_time_study_years")
    op.drop_index("ix_full_time_study_years_code", table_name="full_time_study_years")
    op.drop_index("ix_full_time_study_years_id", table_name="full_time_study_years")
    op.drop_table("full_time_study_years")
