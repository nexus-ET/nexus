"""Add position_index to flowx enrollment tracks for sub-process order.

Revision ID: bb2c3denrolltrackpos
Revises: aa1b2cflowxappform
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "bb2c3denrolltrackpos"
down_revision: Union[str, Sequence[str], None] = "aa1b2cflowxappform"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flowx_enrollment_tracks",
        sa.Column("position_index", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill sequential order within each enrollment + stage.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY enrollment_id, stage_key
                    ORDER BY track_name, id
                ) - 1 AS rn
            FROM flowx_enrollment_tracks
        )
        UPDATE flowx_enrollment_tracks AS t
        SET position_index = ranked.rn
        FROM ranked
        WHERE t.id = ranked.id
        """
    )
    op.alter_column("flowx_enrollment_tracks", "position_index", server_default=None)


def downgrade() -> None:
    op.drop_column("flowx_enrollment_tracks", "position_index")
