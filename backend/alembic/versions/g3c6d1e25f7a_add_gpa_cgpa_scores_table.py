"""add gpa_cgpa_scores table

Revision ID: g3c6d1e25f7a
Revises: f2a4b9c03d5e
Create Date: 2026-06-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g3c6d1e25f7a"
down_revision: Union[str, Sequence[str], None] = "f2a4b9c03d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gpa_cgpa_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_gpa_cgpa_scores_id", "gpa_cgpa_scores", ["id"])
    op.create_index("ix_gpa_cgpa_scores_code", "gpa_cgpa_scores", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_gpa_cgpa_scores_code", table_name="gpa_cgpa_scores")
    op.drop_index("ix_gpa_cgpa_scores_id", table_name="gpa_cgpa_scores")
    op.drop_table("gpa_cgpa_scores")
