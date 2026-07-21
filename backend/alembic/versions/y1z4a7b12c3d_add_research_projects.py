"""add research_projects table

Revision ID: y1z4a7b12c3d
Revises: x0y3z6a01b2c
Create Date: 2026-07-06 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y1z4a7b12c3d"
down_revision: Union[str, Sequence[str], None] = "x0y3z6a01b2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("project_type", sa.String(length=50), nullable=False),
        sa.Column("project_title", sa.String(length=255), nullable=True),
        sa.Column("project_description", sa.Text(), nullable=True),
        sa.Column("publication_url", sa.String(length=500), nullable=True),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_research_projects_lead_id", "research_projects", ["lead_id"])
    op.create_index("ix_research_projects_booking_id", "research_projects", ["booking_id"])
    op.create_index("ix_research_projects_project_type", "research_projects", ["project_type"])


def downgrade() -> None:
    op.drop_index("ix_research_projects_project_type", table_name="research_projects")
    op.drop_index("ix_research_projects_booking_id", table_name="research_projects")
    op.drop_index("ix_research_projects_lead_id", table_name="research_projects")
    op.drop_table("research_projects")
