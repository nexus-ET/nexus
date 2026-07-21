"""add digital_presence_links table

Revision ID: f8g1h4i69j9k
Revises: e7f0g3h58i8j
Create Date: 2026-07-06 27:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8g1h4i69j9k"
down_revision: Union[str, Sequence[str], None] = "e7f0g3h58i8j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "digital_presence_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("platform_name", sa.String(length=50), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("admission_value_note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_digital_presence_links_id", "digital_presence_links", ["id"])
    op.create_index("ix_digital_presence_links_lead_id", "digital_presence_links", ["lead_id"])
    op.create_index("ix_digital_presence_links_booking_id", "digital_presence_links", ["booking_id"])
    op.create_index("ix_digital_presence_links_platform_name", "digital_presence_links", ["platform_name"])
    op.create_index("ix_digital_presence_links_category", "digital_presence_links", ["category"])


def downgrade() -> None:
    op.drop_index("ix_digital_presence_links_category", table_name="digital_presence_links")
    op.drop_index("ix_digital_presence_links_platform_name", table_name="digital_presence_links")
    op.drop_index("ix_digital_presence_links_booking_id", table_name="digital_presence_links")
    op.drop_index("ix_digital_presence_links_lead_id", table_name="digital_presence_links")
    op.drop_index("ix_digital_presence_links_id", table_name="digital_presence_links")
    op.drop_table("digital_presence_links")
