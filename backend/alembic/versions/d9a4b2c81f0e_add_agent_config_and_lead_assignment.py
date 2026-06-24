"""add agent_configs table and assigned_advisor_id on leads

Revision ID: d9a4b2c81f0e
Revises: c8f2a1d94e6b
Create Date: 2026-06-12 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9a4b2c81f0e"
down_revision: Union[str, Sequence[str], None] = "c8f2a1d94e6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("escalation_threshold", sa.Integer(), nullable=False),
        sa.Column("keywords_trigger", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column("leads", sa.Column("assigned_advisor_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_leads_assigned_advisor_id_users",
        "leads",
        "users",
        ["assigned_advisor_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_leads_assigned_advisor_id_users", "leads", type_="foreignkey")
    op.drop_column("leads", "assigned_advisor_id")
    op.drop_table("agent_configs")
