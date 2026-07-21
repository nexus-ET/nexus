"""Add education_courses table for academic framework catalog.

Revision ID: u9v2w18x9y0z
Revises: t8u1v17w9x0y
Create Date: 2026-07-09 21:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "u9v2w18x9y0z"
down_revision: Union[str, Sequence[str], None] = "t8u1v17w9x0y"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "education_courses",
        sa.Column("id", sa.Integer(), sa.Identity(), primary_key=True, nullable=False),
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("levels.id"), nullable=False),
        sa.Column(
            "education_major_id",
            sa.Integer(),
            sa.ForeignKey("education_majors.id"),
            nullable=False,
        ),
        sa.Column(
            "program_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("programs.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("course_level", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("code", name="uq_education_courses_code"),
    )
    op.create_index("ix_education_courses_level_id", "education_courses", ["level_id"])
    op.create_index(
        "ix_education_courses_education_major_id",
        "education_courses",
        ["education_major_id"],
    )
    op.create_index("ix_education_courses_program_id", "education_courses", ["program_id"])
    op.create_index("ix_education_courses_code", "education_courses", ["code"], unique=True)

    op.execute(
        """
        INSERT INTO education_courses (
            level_id,
            education_major_id,
            program_id,
            code,
            label,
            course_level,
            is_active,
            sort_order
        )
        SELECT DISTINCT ON (tc.code)
            p.level_id,
            COALESCE(tc.education_major_id, p.education_major_id),
            COALESCE(tc.qualification_program_id, tp.program_id),
            tc.code,
            tc.label,
            tc.level,
            tc.is_active,
            tc.sort_order
        FROM target_courses tc
        LEFT JOIN target_programs tp ON tp.id = tc.program_id
        JOIN programs p ON p.id = COALESCE(tc.qualification_program_id, tp.program_id)
        WHERE COALESCE(tc.qualification_program_id, tp.program_id) IS NOT NULL
        ORDER BY tc.code, tc.id DESC
        """
    )

    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('education_courses', 'id'),
            COALESCE((SELECT MAX(id) FROM education_courses), 1)
        )
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for education_courses.")
