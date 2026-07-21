"""add candidate_test_scores table

Revision ID: w9x2y5z98a0b
Revises: v8w1x4y87z9a
Create Date: 2026-07-06 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w9x2y5z98a0b"
down_revision: Union[str, Sequence[str], None] = "v8w1x4y87z9a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_test_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("test_name", sa.String(length=20), nullable=False),
        sa.Column("test_date", sa.Date(), nullable=True),
        sa.Column("section_name", sa.String(length=50), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("score_report_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_candidate_test_scores_lead_id", "candidate_test_scores", ["lead_id"])
    op.create_index("ix_candidate_test_scores_booking_id", "candidate_test_scores", ["booking_id"])
    op.create_index("ix_candidate_test_scores_test_name", "candidate_test_scores", ["test_name"])
    op.create_index("ix_candidate_test_scores_created_at", "candidate_test_scores", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_candidate_test_scores_created_at", table_name="candidate_test_scores")
    op.drop_index("ix_candidate_test_scores_test_name", table_name="candidate_test_scores")
    op.drop_index("ix_candidate_test_scores_booking_id", table_name="candidate_test_scores")
    op.drop_index("ix_candidate_test_scores_lead_id", table_name="candidate_test_scores")
    op.drop_table("candidate_test_scores")
