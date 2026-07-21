"""Reset education_majors and related mapping data.

Revision ID: k6l9m5n8o1p2
Revises: j5k8l4m7n9o0
Create Date: 2026-07-13 20:45:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k6l9m5n8o1p2"
down_revision: Union[str, Sequence[str], None] = "j5k8l4m7n9o0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM program_education_major_mappings"))
    bind.execute(sa.text("DELETE FROM education_courses"))
    bind.execute(sa.text("UPDATE target_courses SET education_major_id = NULL"))
    bind.execute(sa.text("DELETE FROM education_major_levels"))
    bind.execute(sa.text("DELETE FROM education_majors"))
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('program_education_major_mappings', 'id'),
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
    raise NotImplementedError("Downgrade not supported for education_majors reset.")
