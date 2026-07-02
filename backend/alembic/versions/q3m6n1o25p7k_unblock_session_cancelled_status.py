"""Allow Lead: Session Cancelled to transition back into the funnel

Revision ID: q3m6n1o25p7k
Revises: p2l5m0n14o6j
Create Date: 2026-06-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "q3m6n1o25p7k"
down_revision: Union[str, Sequence[str], None] = "p2l5m0n14o6j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE status_definitions SET next_stage_id = 4 WHERE id = 6")


def downgrade() -> None:
    op.execute("UPDATE status_definitions SET next_stage_id = NULL WHERE id = 6")
