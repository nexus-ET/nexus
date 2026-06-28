"""add countries table

Revision ID: e1f3a8b92c4d
Revises: d9a4b2c81f0e
Create Date: 2026-06-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f3a8b92c4d"
down_revision: Union[str, Sequence[str], None] = "d9a4b2c81f0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iso2", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("dial_code", sa.String(length=6), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_countries_id", "countries", ["id"])
    op.create_index("ix_countries_iso2", "countries", ["iso2"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_countries_iso2", table_name="countries")
    op.drop_index("ix_countries_id", table_name="countries")
    op.drop_table("countries")
