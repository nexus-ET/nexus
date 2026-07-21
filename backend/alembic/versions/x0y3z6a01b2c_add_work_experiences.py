"""add work_experiences and work_projects tables

Revision ID: x0y3z6a01b2c
Revises: w9x2y5z98a0b
Create Date: 2026-07-06 20:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x0y3z6a01b2c"
down_revision: Union[str, Sequence[str], None] = "w9x2y5z98a0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_experiences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_work_experiences_lead_id", "work_experiences", ["lead_id"])
    op.create_index("ix_work_experiences_booking_id", "work_experiences", ["booking_id"])

    op.create_table(
        "work_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "work_experience_id",
            sa.Integer(),
            sa.ForeignKey("work_experiences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_name", sa.String(length=255), nullable=True),
        sa.Column("project_description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_work_projects_work_experience_id", "work_projects", ["work_experience_id"])


def downgrade() -> None:
    op.drop_index("ix_work_projects_work_experience_id", table_name="work_projects")
    op.drop_table("work_projects")
    op.drop_index("ix_work_experiences_booking_id", table_name="work_experiences")
    op.drop_index("ix_work_experiences_lead_id", table_name="work_experiences")
    op.drop_table("work_experiences")
