"""Allow multiple majors per program mapping.

Revision ID: l7m0n6o9p1q3
Revises: k6l9m5n8o1p2
Create Date: 2026-07-13 21:15:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "l7m0n6o9p1q3"
down_revision: Union[str, Sequence[str], None] = "k6l9m5n8o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_program_education_major_mappings_program_id",
        "program_education_major_mappings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_program_education_major_mappings_program_major",
        "program_education_major_mappings",
        ["program_id", "education_major_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_program_education_major_mappings_program_major",
        "program_education_major_mappings",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_program_education_major_mappings_program_id",
        "program_education_major_mappings",
        ["program_id"],
    )
