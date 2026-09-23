"""Add nullable short_name on businesses.

Revision ID: o3p4q5bizshn
Revises: n2o3p4accfmt
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o3p4q5bizshn"
down_revision: Union[str, Sequence[str], None] = "n2o3p4accfmt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "businesses" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("businesses")}
    if "short_name" not in columns:
        op.add_column(
            "businesses",
            sa.Column("short_name", sa.String(length=80), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "businesses" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("businesses")}
    if "short_name" in columns:
        op.drop_column("businesses", "short_name")
