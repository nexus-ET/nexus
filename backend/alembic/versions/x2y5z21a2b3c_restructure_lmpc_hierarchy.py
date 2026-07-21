"""Restructure Academic Framework to LPMC: Level -> Program -> Major -> Course.

Revision ID: x2y5z21a2b3c
Revises: w1x4y20z1a2b
Create Date: 2026-07-09 23:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "x2y5z21a2b3c"
down_revision: Union[str, Sequence[str], None] = "w1x4y20z1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "education_majors",
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_education_majors_program_id",
        "education_majors",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_education_majors_program_id", "education_majors", ["program_id"])

    bind.execute(
        sa.text(
            """
            UPDATE education_majors em
            SET program_id = p.id
            FROM programs p
            WHERE p.education_major_id = em.id
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE education_courses ec
            SET level_id = p.level_id,
                program_id = em.program_id
            FROM education_majors em
            JOIN programs p ON p.id = em.program_id
            WHERE ec.education_major_id = em.id
            """
        )
    )

    op.drop_constraint("uq_programs_level_education_major", "programs", type_="unique")
    op.drop_index("ix_programs_education_major_id", table_name="programs")
    op.drop_constraint(
        "programs_education_major_id_fkey", "programs", type_="foreignkey"
    )
    op.drop_column("programs", "education_major_id")

    op.alter_column("education_courses", "level_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        "education_courses",
        "program_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("education_major_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "programs_education_major_id_fkey",
        "programs",
        "education_majors",
        ["education_major_id"],
        ["id"],
    )
    op.create_index("ix_programs_education_major_id", "programs", ["education_major_id"])
    op.create_unique_constraint(
        "uq_programs_level_education_major",
        "programs",
        ["level_id", "education_major_id"],
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE programs p
            SET education_major_id = em.id
            FROM education_majors em
            WHERE em.program_id = p.id
            """
        )
    )

    op.alter_column("programs", "education_major_id", nullable=False)

    op.alter_column(
        "education_courses",
        "program_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column("education_courses", "level_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_education_majors_program_id", table_name="education_majors")
    op.drop_constraint("fk_education_majors_program_id", "education_majors", type_="foreignkey")
    op.drop_column("education_majors", "program_id")
