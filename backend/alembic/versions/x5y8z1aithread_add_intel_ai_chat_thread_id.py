"""Add thread_id to intel_ai_chat_logs for multi-turn sessions.

Revision ID: x5y8z1aithread
Revises: w4x7z0intaichat
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "x5y8z1aithread"
down_revision = "w4x7z0intaichat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("intel_ai_chat_logs"):
        return
    cols = {c["name"] for c in inspector.get_columns("intel_ai_chat_logs")}
    indexes = {i["name"] for i in inspector.get_indexes("intel_ai_chat_logs")}
    if "thread_id" not in cols:
        op.add_column(
            "intel_ai_chat_logs",
            sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
    if "ix_intel_ai_chat_logs_thread_id" not in indexes:
        op.create_index("ix_intel_ai_chat_logs_thread_id", "intel_ai_chat_logs", ["thread_id"])
    if "ix_intel_ai_chat_logs_user_thread_created" not in indexes:
        op.create_index(
            "ix_intel_ai_chat_logs_user_thread_created",
            "intel_ai_chat_logs",
            ["user_id", "thread_id", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_intel_ai_chat_logs_user_thread_created", table_name="intel_ai_chat_logs")
    op.drop_index("ix_intel_ai_chat_logs_thread_id", table_name="intel_ai_chat_logs")
    op.drop_column("intel_ai_chat_logs", "thread_id")
