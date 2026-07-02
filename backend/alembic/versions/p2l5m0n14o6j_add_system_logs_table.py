"""add system_logs table for automation diagnostics

Revision ID: p2l5m0n14o6j
Revises: o1k4l9m03n5i
Create Date: 2026-06-13 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2l5m0n14o6j"
down_revision: Union[str, Sequence[str], None] = "o1k4l9m03n5i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "level",
            sa.Enum("info", "warning", "error", name="system_log_level", native_enum=False),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["leads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_logs_id", "system_logs", ["id"])
    op.create_index("ix_system_logs_level", "system_logs", ["level"])
    op.create_index("ix_system_logs_source", "system_logs", ["source"])
    op.create_index("ix_system_logs_student_id", "system_logs", ["student_id"])
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_created_at", table_name="system_logs")
    op.drop_index("ix_system_logs_student_id", table_name="system_logs")
    op.drop_index("ix_system_logs_source", table_name="system_logs")
    op.drop_index("ix_system_logs_level", table_name="system_logs")
    op.drop_index("ix_system_logs_id", table_name="system_logs")
    op.drop_table("system_logs")
