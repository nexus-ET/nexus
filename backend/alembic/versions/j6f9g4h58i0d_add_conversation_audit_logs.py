"""add conversation_audit_logs table

Revision ID: j6f9g4h58i0d
Revises: i5e8f3g47h9c
Create Date: 2026-06-28 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j6f9g4h58i0d"
down_revision: Union[str, Sequence[str], None] = "i5e8f3g47h9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_reply", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_model", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("escalated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_conversation_audit_logs_lead_id", "conversation_audit_logs", ["lead_id"])
    op.create_index("ix_conversation_audit_logs_escalated", "conversation_audit_logs", ["escalated"])
    op.create_index("ix_conversation_audit_logs_created_at", "conversation_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_conversation_audit_logs_created_at", table_name="conversation_audit_logs")
    op.drop_index("ix_conversation_audit_logs_escalated", table_name="conversation_audit_logs")
    op.drop_index("ix_conversation_audit_logs_lead_id", table_name="conversation_audit_logs")
    op.drop_table("conversation_audit_logs")
