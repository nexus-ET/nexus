"""Add optional education_sub_major_id on program-major mappings.

Revision ID: rr8s9tsubmap
Revises: qq7r8soffidx
Create Date: 2026-08-20 08:20:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision: str = "rr8s9tsubmap"
down_revision: Union[str, Sequence[str], None] = "qq7r8soffidx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "program_education_major_mappings"
_COLUMN = "education_sub_major_id"
_INDEX = "ix_program_education_major_mappings_education_sub_major_id"
_FK = "fk_program_education_major_mappings_education_sub_major_id"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))
    op.create_index(_INDEX, _TABLE, [_COLUMN])
    op.create_foreign_key(
        _FK,
        _TABLE,
        "education_sub_majors",
        [_COLUMN],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    inspector = sa_inspect(bind)
    if not inspector.has_table("temp_programs"):
        return
    temp_cols = {column["name"] for column in inspector.get_columns("temp_programs")}
    if not {"id", "course_code", "sub_department"}.issubset(temp_cols):
        return

    # programs.code = left(course_code || '-' || temp id, 50) from the temp load.
    op.execute(
        sa.text(
            """
            UPDATE program_education_major_mappings AS map
            SET education_sub_major_id = s.id
            FROM programs p
            JOIN temp_programs tp
              ON p.code = left(tp.course_code || '-' || tp.id::text, 50)
            JOIN education_sub_majors s
              ON lower(btrim(s.name)) = lower(btrim(tp.sub_department))
            WHERE map.program_id = p.id
              AND s.major_id = map.education_major_id
              AND map.education_sub_major_id IS NULL
              AND tp.sub_department IS NOT NULL
              AND btrim(tp.sub_department) <> ''
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint(_FK, _TABLE, type_="foreignkey")
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
