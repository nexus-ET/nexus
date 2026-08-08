"""Add is_optional to flowx_tasks; keep dropped templates on country boards.

Revision ID: cc3d4etaskoptional
Revises: bb2c3denrolltrackpos
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cc3d4etaskoptional"
down_revision: Union[str, Sequence[str], None] = "bb2c3denrolltrackpos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flowx_tasks",
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Dropped (waive) templates stay on the country board — reactivate any previously hidden ones.
    op.execute(
        """
        UPDATE flowx_task_templates
        SET is_active = true
        WHERE override_action = 'waive' AND is_active = false
        """
    )


def downgrade() -> None:
    op.drop_column("flowx_tasks", "is_optional")
