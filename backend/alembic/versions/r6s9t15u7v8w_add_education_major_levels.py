"""Add education_major_levels mapping table.

Revision ID: r6s9t15u7v8w
Revises: q5r8s14t6u7v
Create Date: 2026-07-09 07:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r6s9t15u7v8w"
down_revision: Union[str, Sequence[str], None] = "q5r8s14t6u7v"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "education_major_levels",
        sa.Column("education_major_id", sa.Integer(), nullable=False),
        sa.Column("level_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["education_major_id"], ["education_majors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["level_id"], ["levels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("education_major_id", "level_id"),
    )
    op.create_index(
        "ix_education_major_levels_level_id",
        "education_major_levels",
        ["level_id"],
    )
    # Existing majors apply to all current levels until explicitly narrowed.
    op.execute(
        """
        INSERT INTO education_major_levels (education_major_id, level_id)
        SELECT em.id, l.id
        FROM education_majors em
        CROSS JOIN levels l
        WHERE NOT EXISTS (
            SELECT 1
            FROM education_major_levels eml
            WHERE eml.education_major_id = em.id
              AND eml.level_id = l.id
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_education_major_levels_level_id", table_name="education_major_levels")
    op.drop_table("education_major_levels")
