"""Add color column to education_majors.

Revision ID: i4j7k3l6m8n9
Revises: h3i6j2k5l7m8
Create Date: 2026-07-13 20:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "i4j7k3l6m8n9"
down_revision: Union[str, Sequence[str], None] = "h3i6j2k5l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAJOR_COLOR_PALETTE = (
    "#6366F1",
    "#8B5CF6",
    "#EC4899",
    "#F43F5E",
    "#F97316",
    "#EAB308",
    "#22C55E",
    "#14B8A6",
    "#06B6D4",
    "#3B82F6",
    "#A855F7",
    "#84CC16",
)


def upgrade() -> None:
    op.add_column(
        "education_majors",
        sa.Column("color", sa.String(length=7), nullable=True),
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, label
            FROM education_majors
            ORDER BY id ASC
            """
        )
    ).fetchall()

    used_colors: set[str] = set()
    for index, row in enumerate(rows):
        major_id = row.id
        label = row.label or ""
        color = next(
            (candidate for candidate in MAJOR_COLOR_PALETTE if candidate not in used_colors),
            MAJOR_COLOR_PALETTE[index % len(MAJOR_COLOR_PALETTE)],
        )
        used_colors.add(color)
        bind.execute(
            sa.text("UPDATE education_majors SET color = :color WHERE id = :major_id"),
            {"color": color, "major_id": major_id},
        )


def downgrade() -> None:
    op.drop_column("education_majors", "color")
