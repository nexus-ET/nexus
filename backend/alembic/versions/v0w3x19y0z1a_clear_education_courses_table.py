"""Clear education_courses for manual UI entry.

Revision ID: v0w3x19y0z1a
Revises: u9v2w18x9y0z
Create Date: 2026-07-09 22:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v0w3x19y0z1a"
down_revision: Union[str, Sequence[str], None] = "u9v2w18x9y0z"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM education_courses"))
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('education_courses', 'id'),
                1,
                false
            )
            """
        )
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for education_courses clear.")
