"""Heal never-attempted institution publish failures to pending.

Revision ID: b3c6d9e42f5g
Revises: a2b5c8d31e4f
Create Date: 2026-07-20 08:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b3c6d9e42f5g"
down_revision: Union[str, Sequence[str], None] = "a2b5c8d31e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Institutions never published should not appear as Failure.
    op.execute(
        """
        UPDATE institutions
        SET publish_status = 'pending',
            last_publish_error = NULL
        WHERE last_publish_attempt_at IS NULL
          AND publish_status = 'failure'
        """
    )


def downgrade() -> None:
    # Irreversible data heal — leave pending rows as-is.
    pass
