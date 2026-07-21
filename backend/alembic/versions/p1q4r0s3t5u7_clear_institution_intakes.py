"""Clear institution_intakes for a fresh start.

Revision ID: p1q4r0s3t5u7
Revises: o0p3q9r2s4t6
Create Date: 2026-07-15 11:16:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "p1q4r0s3t5u7"
down_revision: Union[str, Sequence[str], None] = "o0p3q9r2s4t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # Child rows first (assignments cascade on FK, but clear explicitly for safety).
    bind.execute(sa.text("DELETE FROM program_intake_assignments"))
    bind.execute(sa.text("DELETE FROM calendar_intake_alert_logs"))
    # Self-referencing parent_intake_id: clear links then rows.
    bind.execute(sa.text("UPDATE institution_intakes SET parent_intake_id = NULL"))
    bind.execute(sa.text("DELETE FROM institution_intakes"))
    bind.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('institution_intakes', 'id'),
                1,
                false
            )
            """
        )
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for institution_intakes clear.")
