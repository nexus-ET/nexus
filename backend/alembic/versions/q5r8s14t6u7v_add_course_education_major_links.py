"""Link target_courses to education_majors and qualification programs.

Revision ID: q5r8s14t6u7v
Revises: p4q7r03s5t6u
Create Date: 2026-07-09 06:40:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "q5r8s14t6u7v"
down_revision: Union[str, Sequence[str], None] = "p4q7r03s5t6u"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "target_courses",
        sa.Column("education_major_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "target_courses",
        sa.Column(
            "qualification_program_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_target_courses_education_major_id",
        "target_courses",
        "education_majors",
        ["education_major_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_target_courses_qualification_program_id",
        "target_courses",
        "programs",
        ["qualification_program_id"],
        ["id"],
    )
    op.execute(
        """
        UPDATE target_courses tc
        SET qualification_program_id = tp.program_id
        FROM target_programs tp
        WHERE tc.program_id = tp.id
          AND tc.qualification_program_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE target_courses tc
        SET education_major_id = em.id
        FROM target_programs tp
        JOIN education_majors em
          ON lower(em.label) = lower(tp.label)
          OR upper(em.code) = upper(tp.code)
        WHERE tc.program_id = tp.id
          AND tc.education_major_id IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_courses_education_major_id "
        "ON target_courses (education_major_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_courses_qualification_program_id "
        "ON target_courses (qualification_program_id)"
    )


def downgrade() -> None:
    op.drop_index("ix_target_courses_qualification_program_id", table_name="target_courses")
    op.drop_index("ix_target_courses_education_major_id", table_name="target_courses")
    op.drop_constraint(
        "fk_target_courses_qualification_program_id",
        "target_courses",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_target_courses_education_major_id",
        "target_courses",
        type_="foreignkey",
    )
    op.drop_column("target_courses", "qualification_program_id")
    op.drop_column("target_courses", "education_major_id")
