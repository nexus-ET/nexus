"""add counselling_notes table

Revision ID: k7g0h5i69j1e
Revises: j6f9g4h58i0d
Create Date: 2026-06-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k7g0h5i69j1e"
down_revision: Union[str, Sequence[str], None] = "j6f9g4h58i0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "counselling_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "admin_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ai_transcription", sa.Text(), nullable=True),
        sa.Column("preferred_universities", sa.Text(), nullable=True),
        sa.Column("scholarship_interests", sa.Text(), nullable=True),
        sa.Column("career_goals", sa.Text(), nullable=True),
        sa.Column("officer_recommendations", sa.Text(), nullable=True),
        sa.Column("next_follow_up", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_counselling_notes_id", "counselling_notes", ["id"])
    op.create_index("ix_counselling_notes_booking_id", "counselling_notes", ["booking_id"], unique=True)
    op.create_index("ix_counselling_notes_admin_id", "counselling_notes", ["admin_id"])


def downgrade() -> None:
    op.drop_index("ix_counselling_notes_admin_id", table_name="counselling_notes")
    op.drop_index("ix_counselling_notes_booking_id", table_name="counselling_notes")
    op.drop_index("ix_counselling_notes_id", table_name="counselling_notes")
    op.drop_table("counselling_notes")
