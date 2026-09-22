"""add target_completion_date to counselor_followup_logs

Revision ID: i7j8k9followdt
Revises: h6i7j8followup
Create Date: 2026-09-20 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i7j8k9followdt"
down_revision: Union[str, Sequence[str], None] = "h6i7j8followup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "counselor_followup_logs",
        sa.Column("target_completion_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("counselor_followup_logs", "target_completion_date")
