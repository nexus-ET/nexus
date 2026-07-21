"""Ensure FK indexes exist on academic hierarchy tables for cascade filters.

Revision ID: p4q7r03s5t6u
Revises: o3p6q9r02s4n
Create Date: 2026-07-08 21:20:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "p4q7r03s5t6u"
down_revision: Union[str, Sequence[str], None] = "o3p6q9r02s4n"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent index creation for hierarchy filter performance.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_programs_level_id ON programs (level_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_programs_program_id ON target_programs (program_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_target_courses_program_id ON target_courses (program_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_education_degrees_level_id ON education_degrees (level_id)"
    )


def downgrade() -> None:
    # Keep base indexes from table creation; only drop ones we may have added exclusively here.
    # Safe no-ops if indexes are required elsewhere.
    pass
