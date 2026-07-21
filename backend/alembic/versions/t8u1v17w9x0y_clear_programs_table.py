"""Clear programs table for manual UI entry.

Revision ID: t8u1v17w9x0y
Revises: s7t0u16v8w9x
Create Date: 2026-07-09 20:20:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t8u1v17w9x0y"
down_revision: Union[str, Sequence[str], None] = "s7t0u16v8w9x"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text("DELETE FROM institution_course_offerings"))
    bind.execute(sa.text("DELETE FROM target_courses"))
    bind.execute(sa.text("DELETE FROM target_programs"))
    bind.execute(sa.text("DELETE FROM programs"))


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for programs clear.")
