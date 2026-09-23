"""Store checklist email receipt fields on counselor follow-up logs.

Revision ID: p4q5r6chkrcp
Revises: o3p4q5bizshn
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p4q5r6chkrcp"
down_revision: Union[str, Sequence[str], None] = "o3p4q5bizshn"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JsonColumn = sa.JSON().with_variant(
    postgresql.JSONB(astext_type=sa.Text()),
    "postgresql",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "counselor_followup_logs" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("counselor_followup_logs")}
    if "checklist_email_to" not in columns:
        op.add_column(
            "counselor_followup_logs",
            sa.Column("checklist_email_to", sa.String(length=255), nullable=True),
        )
    if "checklist_email_sent_at" not in columns:
        op.add_column(
            "counselor_followup_logs",
            sa.Column("checklist_email_sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "checklist_sent_documents" not in columns:
        op.add_column(
            "counselor_followup_logs",
            sa.Column("checklist_sent_documents", JsonColumn, nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "counselor_followup_logs" not in tables:
        return

    columns = {col["name"] for col in inspector.get_columns("counselor_followup_logs")}
    if "checklist_sent_documents" in columns:
        op.drop_column("counselor_followup_logs", "checklist_sent_documents")
    if "checklist_email_sent_at" in columns:
        op.drop_column("counselor_followup_logs", "checklist_email_sent_at")
    if "checklist_email_to" in columns:
        op.drop_column("counselor_followup_logs", "checklist_email_to")
