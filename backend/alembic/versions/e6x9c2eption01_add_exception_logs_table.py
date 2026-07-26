"""add exception_logs table for Insights Exception Report

Revision ID: e6x9c2eption01
Revises: d5e8f1a64h7i
Create Date: 2026-07-23 19:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6x9c2eption01"
down_revision: Union[str, Sequence[str], None] = "d5e8f1a64h7i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exception_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_by_user", sa.String(length=255), nullable=False),
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("page_path", sa.String(length=255), nullable=True),
        sa.Column("exception_type", sa.String(length=120), nullable=True),
        sa.Column("related_resource", sa.String(length=100), nullable=True),
        sa.Column("related_id", sa.String(length=100), nullable=True),
        sa.Column("attempt_timestamp", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exception_logs_id", "exception_logs", ["id"])
    op.create_index("ix_exception_logs_severity", "exception_logs", ["severity"])
    op.create_index("ix_exception_logs_source", "exception_logs", ["source"])
    op.create_index("ix_exception_logs_category", "exception_logs", ["category"])
    op.create_index("ix_exception_logs_status", "exception_logs", ["status"])
    op.create_index("ix_exception_logs_triggered_by_user", "exception_logs", ["triggered_by_user"])
    op.create_index(
        "ix_exception_logs_triggered_by_user_id", "exception_logs", ["triggered_by_user_id"]
    )
    op.create_index("ix_exception_logs_attempt_timestamp", "exception_logs", ["attempt_timestamp"])
    op.create_index("ix_exception_logs_created_at", "exception_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_exception_logs_created_at", table_name="exception_logs")
    op.drop_index("ix_exception_logs_attempt_timestamp", table_name="exception_logs")
    op.drop_index("ix_exception_logs_triggered_by_user_id", table_name="exception_logs")
    op.drop_index("ix_exception_logs_triggered_by_user", table_name="exception_logs")
    op.drop_index("ix_exception_logs_status", table_name="exception_logs")
    op.drop_index("ix_exception_logs_category", table_name="exception_logs")
    op.drop_index("ix_exception_logs_source", table_name="exception_logs")
    op.drop_index("ix_exception_logs_severity", table_name="exception_logs")
    op.drop_index("ix_exception_logs_id", table_name="exception_logs")
    op.drop_table("exception_logs")
