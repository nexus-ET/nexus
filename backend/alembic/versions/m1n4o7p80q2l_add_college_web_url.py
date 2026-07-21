"""add college web_url

Revision ID: m1n4o7p80q2l
Revises: l0m3n6o79p1k
Create Date: 2026-07-08 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1n4o7p80q2l"
down_revision: Union[str, Sequence[str], None] = "l0m3n6o79p1k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("colleges", sa.Column("web_url", sa.String(length=250), nullable=True))


def downgrade() -> None:
    op.drop_column("colleges", "web_url")
