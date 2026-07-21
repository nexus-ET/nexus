"""Add course-to-major mapping table for multi-major courses.

Revision ID: n9o2p8q1r3s5
Revises: m8n1o7p0q2r4
Create Date: 2026-07-14 21:15:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "n9o2p8q1r3s5"
down_revision: Union[str, Sequence[str], None] = "m8n1o7p0q2r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "course_education_major_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("education_major_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["education_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["education_major_id"], ["education_majors.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "course_id",
            "education_major_id",
            name="uq_course_education_major_mappings_course_major",
        ),
    )
    op.create_index(
        "ix_course_education_major_mappings_course_id",
        "course_education_major_mappings",
        ["course_id"],
    )
    op.create_index(
        "ix_course_education_major_mappings_education_major_id",
        "course_education_major_mappings",
        ["education_major_id"],
    )
    op.execute(
        """
        INSERT INTO course_education_major_mappings (course_id, education_major_id)
        SELECT id, education_major_id
        FROM education_courses
        WHERE education_major_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_course_education_major_mappings_education_major_id",
        table_name="course_education_major_mappings",
    )
    op.drop_index(
        "ix_course_education_major_mappings_course_id",
        table_name="course_education_major_mappings",
    )
    op.drop_table("course_education_major_mappings")
