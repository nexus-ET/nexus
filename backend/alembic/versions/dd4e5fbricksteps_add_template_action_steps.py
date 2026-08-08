"""Add action_steps to flowx_task_templates for sub-process hover checklists.

Revision ID: dd4e5fbricksteps
Revises: cc3d4etaskoptional
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "dd4e5fbricksteps"
down_revision: Union[str, Sequence[str], None] = "cc3d4etaskoptional"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flowx_task_templates",
        sa.Column("action_steps", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("flowx_task_templates", "action_steps")
