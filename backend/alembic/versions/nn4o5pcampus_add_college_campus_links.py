"""add source-backed college campus links

Revision ID: nn4o5pcampus
Revises: mm3n4oinquiryhub
Create Date: 2026-08-15 16:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "nn4o5pcampus"
down_revision: Union[str, Sequence[str], None] = "mm3n4oinquiryhub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "college_campuses",
        sa.Column(
            "college_id",
            sa.Integer(),
            sa.ForeignKey("colleges.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "campus_id",
            sa.Integer(),
            sa.ForeignKey("campuses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "is_primary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
    )
    op.create_index("ix_college_campuses_campus_id", "college_campuses", ["campus_id"])
    op.execute(
        """
        INSERT INTO college_campuses (college_id, campus_id, is_primary)
        SELECT id, campus_id, TRUE
        FROM colleges
        WHERE campus_id IS NOT NULL
        ON CONFLICT (college_id, campus_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_college_campuses_campus_id", table_name="college_campuses")
    op.drop_table("college_campuses")
