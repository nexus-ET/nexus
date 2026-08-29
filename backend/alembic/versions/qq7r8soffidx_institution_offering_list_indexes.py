"""Add offering indexes used by the institution summary list.

Revision ID: qq7r8soffidx
Revises: pp6q7rinstfields
Create Date: 2026-08-19 22:10:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "qq7r8soffidx"
down_revision: Union[str, Sequence[str], None] = "pp6q7rinstfields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_institution_course_offerings_course_id "
        "ON institution_course_offerings (course_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_institution_course_offerings_inst_active_course "
        "ON institution_course_offerings (institution_id, is_active, course_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_courses_qualification_program_id "
        "ON target_courses (qualification_program_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_courses_education_major_id "
        "ON target_courses (education_major_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_programs_level_id ON programs (level_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_institution_course_offerings_inst_active_course")
    op.execute("DROP INDEX IF EXISTS ix_institution_course_offerings_course_id")
    # qualification_program_id / education_major_id / programs.level_id indexes
    # may pre-exist from earlier migrations; leave them in place on downgrade.
