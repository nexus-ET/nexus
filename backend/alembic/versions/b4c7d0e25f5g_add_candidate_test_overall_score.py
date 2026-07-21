"""add overall_score to candidate_test_scores

Revision ID: b4c7d0e25f5g
Revises: a3b6c9d02e4f
Create Date: 2026-07-06 23:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4c7d0e25f5g"
down_revision: Union[str, Sequence[str], None] = "a3b6c9d02e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "candidate_test_scores",
        sa.Column("overall_score", sa.Numeric(precision=6, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidate_test_scores", "overall_score")
