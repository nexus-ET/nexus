"""Add user_id+created_at index for Intel AI thread sidebar queries.

Revision ID: y6z9a2bithreadsx
Revises: x5y8z1aithread
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "y6z9a2bithreadsx"
down_revision = "x5y8z1aithread"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fast sidebar / date-bucket scans: filter by user, order by recency.
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_intel_ai_chat_logs_user_created "
            "ON intel_ai_chat_logs (user_id, created_at)"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_intel_ai_chat_logs_user_created", table_name="intel_ai_chat_logs")
