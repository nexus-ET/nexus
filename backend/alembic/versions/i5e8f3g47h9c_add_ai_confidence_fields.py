"""add ai confidence fields on messages and leads

Revision ID: i5e8f3g47h9c
Revises: h4d7e2f36g8b
Create Date: 2026-06-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i5e8f3g47h9c"
down_revision: Union[str, Sequence[str], None] = "h4d7e2f36g8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("ai_confidence", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("handoff_ai_confidence", sa.Float(), nullable=True))
    op.add_column("leads", sa.Column("handoff_reason", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE agent_configs
        SET ai_model = 'openai:' || ai_model
        WHERE ai_model NOT LIKE '%:%'
        """
    )


def downgrade() -> None:
    op.drop_column("leads", "handoff_reason")
    op.drop_column("leads", "handoff_ai_confidence")
    op.drop_column("messages", "ai_confidence")
