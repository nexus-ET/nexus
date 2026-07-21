"""Persist cascade-to-children preference on institution intakes.

Revision ID: r3s6t2u5v7w9
Revises: q2r5s1t4u6v8
Create Date: 2026-07-15 16:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "r3s6t2u5v7w9"
down_revision: Union[str, Sequence[str], None] = "q2r5s1t4u6v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "institution_intakes",
        sa.Column(
            "cascade_to_children",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # Backfill: parents that already have cascaded child rows preferred cascade.
    op.execute(
        """
        UPDATE institution_intakes AS parent
        SET cascade_to_children = true
        WHERE EXISTS (
            SELECT 1
            FROM institution_intakes AS child
            WHERE child.parent_intake_id = parent.id
        )
        """
    )


def downgrade() -> None:
    op.drop_column("institution_intakes", "cascade_to_children")
