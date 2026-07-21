"""Clear education majors and their program/level mappings.

Revision ID: h3i6j2k5l7m8
Revises: g2h5i1j4k5l6
Create Date: 2026-07-13 20:05:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "h3i6j2k5l7m8"
down_revision: Union[str, Sequence[str], None] = "g2h5i1j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM education_courses"))
    bind.execute(sa.text("UPDATE target_courses SET education_major_id = NULL"))
    bind.execute(sa.text("DELETE FROM education_major_levels"))
    bind.execute(sa.text("DELETE FROM education_majors"))
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
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('education_majors', 'id'),
                1,
                false
            )
            """
        )
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for education_majors clear.")
