"""add resolution_comment to exception_logs

Revision ID: f7y0d3esolution
Revises: e6x9c2eption01
Create Date: 2026-07-26 08:12:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7y0d3esolution"
down_revision: Union[str, Sequence[str], None] = "e6x9c2eption01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "exception_logs",
        sa.Column("resolution_comment", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exception_logs", "resolution_comment")
