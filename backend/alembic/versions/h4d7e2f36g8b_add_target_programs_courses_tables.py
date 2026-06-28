"""add target_programs and target_courses tables

Revision ID: h4d7e2f36g8b
Revises: g3c6d1e25f7a
Create Date: 2026-06-27 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4d7e2f36g8b"
down_revision: Union[str, Sequence[str], None] = "g3c6d1e25f7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "target_programs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_target_programs_id", "target_programs", ["id"])
    op.create_index("ix_target_programs_code", "target_programs", ["code"], unique=True)

    op.create_table(
        "target_courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), sa.ForeignKey("target_programs.id"), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_target_courses_id", "target_courses", ["id"])
    op.create_index("ix_target_courses_code", "target_courses", ["code"], unique=True)
    op.create_index("ix_target_courses_program_id", "target_courses", ["program_id"])


def downgrade() -> None:
    op.drop_index("ix_target_courses_program_id", table_name="target_courses")
    op.drop_index("ix_target_courses_code", table_name="target_courses")
    op.drop_index("ix_target_courses_id", table_name="target_courses")
    op.drop_table("target_courses")
    op.drop_index("ix_target_programs_code", table_name="target_programs")
    op.drop_index("ix_target_programs_id", table_name="target_programs")
    op.drop_table("target_programs")
