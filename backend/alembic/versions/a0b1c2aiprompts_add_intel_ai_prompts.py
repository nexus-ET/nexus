"""Add intel_ai_prompts table for saved AI Assistant prompts.

Revision ID: a0b1c2aiprompts
Revises: zz6a7bbizctc
Create Date: 2026-09-03
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a0b1c2aiprompts"
down_revision: Union[str, Sequence[str], None] = "zz6a7bbizctc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intel_ai_prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="private"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intel_ai_prompts_owner_user_id", "intel_ai_prompts", ["owner_user_id"])
    op.create_index("ix_intel_ai_prompts_visibility", "intel_ai_prompts", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_intel_ai_prompts_visibility", table_name="intel_ai_prompts")
    op.drop_index("ix_intel_ai_prompts_owner_user_id", table_name="intel_ai_prompts")
    op.drop_table("intel_ai_prompts")
