"""Add lead_status_change_logs for active/inactive audit trail.

Revision ID: g5h6i7leadact
Revises: f4g5h6scanxgrp
Create Date: 2026-09-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g5h6i7leadact"
down_revision: Union[str, Sequence[str], None] = "f4g5h6scanxgrp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lead_status_change_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "lead_id",
            sa.Integer(),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=20), nullable=False),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column(
            "reasons",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("changed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_lead_status_change_logs_lead_id",
        "lead_status_change_logs",
        ["lead_id"],
    )
    op.create_index(
        "ix_lead_status_change_logs_created_at",
        "lead_status_change_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_status_change_logs_created_at", table_name="lead_status_change_logs")
    op.drop_index("ix_lead_status_change_logs_lead_id", table_name="lead_status_change_logs")
    op.drop_table("lead_status_change_logs")
