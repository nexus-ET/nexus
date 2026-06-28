"""add education_degrees table

Revision ID: f2a4b9c03d5e
Revises: e1f3a8b92c4d
Create Date: 2026-06-27 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a4b9c03d5e"
down_revision: Union[str, Sequence[str], None] = "e1f3a8b92c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "education_degrees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_education_degrees_id", "education_degrees", ["id"])
    op.create_index("ix_education_degrees_code", "education_degrees", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_education_degrees_code", table_name="education_degrees")
    op.drop_index("ix_education_degrees_id", table_name="education_degrees")
    op.drop_table("education_degrees")
