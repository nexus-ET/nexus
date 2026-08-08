"""Add checklist_state JSONB on flowx_tasks for activity checklist progress.

Revision ID: hh8i9jchecklist
Revises: gg7h8iparentcasc
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "hh8i9jchecklist"
down_revision: Union[str, Sequence[str], None] = "gg7h8iparentcasc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("flowx_tasks"):
        return
    cols = {c["name"] for c in inspector.get_columns("flowx_tasks")}
    if "checklist_state" in cols:
        return
    op.add_column(
        "flowx_tasks",
        sa.Column(
            "checklist_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("flowx_tasks", "checklist_state")
