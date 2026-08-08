"""Add intake_assessment JSONB on counselling_bookings for 1.1 counselor workspace.

Revision ID: ii9j0kintakeass
Revises: hh8i9jchecklist
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ii9j0kintakeass"
down_revision: Union[str, Sequence[str], None] = "hh8i9jchecklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    cols = {c["name"] for c in inspector.get_columns("counselling_bookings")}
    if "intake_assessment" in cols:
        return
    op.add_column(
        "counselling_bookings",
        sa.Column(
            "intake_assessment",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("counselling_bookings", "intake_assessment")
