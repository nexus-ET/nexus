"""add non_academic_activities table

Revision ID: z2a5b8c13d4e
Revises: y1z4a7b12c3d
Create Date: 2026-07-06 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z2a5b8c13d4e"
down_revision: Union[str, Sequence[str], None] = "y1z4a7b12c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "non_academic_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("activity_category", sa.String(length=50), nullable=True),
        sa.Column("activity_name", sa.String(length=255), nullable=True),
        sa.Column("role_or_title", sa.String(length=100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_non_academic_activities_lead_id", "non_academic_activities", ["lead_id"])
    op.create_index("ix_non_academic_activities_booking_id", "non_academic_activities", ["booking_id"])
    op.create_index(
        "ix_non_academic_activities_activity_category",
        "non_academic_activities",
        ["activity_category"],
    )


def downgrade() -> None:
    op.drop_index("ix_non_academic_activities_activity_category", table_name="non_academic_activities")
    op.drop_index("ix_non_academic_activities_booking_id", table_name="non_academic_activities")
    op.drop_index("ix_non_academic_activities_lead_id", table_name="non_academic_activities")
    op.drop_table("non_academic_activities")
