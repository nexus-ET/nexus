"""Add intel_ai_chat_logs for Nexus Intel AI Assistant audit trail.

Revision ID: w4x7z0intaichat
Revises: v3w6x9glossaryexp
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w4x7z0intaichat"
down_revision = "v3w6x9glossaryexp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intel_ai_chat_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("retrieved_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_intel_ai_chat_logs_user_id", "intel_ai_chat_logs", ["user_id"])
    op.create_index("ix_intel_ai_chat_logs_created_at", "intel_ai_chat_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_intel_ai_chat_logs_created_at", table_name="intel_ai_chat_logs")
    op.drop_index("ix_intel_ai_chat_logs_user_id", table_name="intel_ai_chat_logs")
    op.drop_table("intel_ai_chat_logs")
