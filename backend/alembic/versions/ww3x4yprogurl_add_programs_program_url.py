"""Add programs.program_url for university program weblinks.

Revision ID: ww3x4yprogurl
Revises: vv2w3xprogserial
Create Date: 2026-08-21 22:55:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "ww3x4yprogurl"
down_revision: Union[str, Sequence[str], None] = "vv2w3xprogserial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("programs"):
        return
    cols = {c["name"] for c in inspector.get_columns("programs")}
    if "program_url" not in cols:
        op.add_column(
            "programs",
            sa.Column("program_url", sa.String(length=2048), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("programs"):
        return
    cols = {c["name"] for c in inspector.get_columns("programs")}
    if "program_url" in cols:
        op.drop_column("programs", "program_url")
