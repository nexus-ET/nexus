"""add candidate_educations table

Revision ID: c5d8e1f36g6h
Revises: b4c7d0e25f5g
Create Date: 2026-07-06 24:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5d8e1f36g6h"
down_revision: Union[str, Sequence[str], None] = "b4c7d0e25f5g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_educations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("degree_code", sa.String(length=50), nullable=True),
        sa.Column("degree_other", sa.String(length=255), nullable=True),
        sa.Column("major", sa.String(length=255), nullable=True),
        sa.Column("university_name", sa.String(length=255), nullable=True),
        sa.Column("university_affiliation", sa.String(length=255), nullable=True),
        sa.Column("graduation_month", sa.Integer(), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("gpa_cgpa_code", sa.String(length=50), nullable=True),
        sa.Column("gpa_cgpa_other", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_candidate_educations_lead_id", "candidate_educations", ["lead_id"])
    op.create_index("ix_candidate_educations_booking_id", "candidate_educations", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_educations_booking_id", table_name="candidate_educations")
    op.drop_index("ix_candidate_educations_lead_id", table_name="candidate_educations")
    op.drop_table("candidate_educations")
