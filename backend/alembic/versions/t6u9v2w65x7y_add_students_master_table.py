"""add students_master table

Revision ID: t6u9v2w65x7y
Revises: s5p8q1r54s0m
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t6u9v2w65x7y"
down_revision: Union[str, Sequence[str], None] = "s5p8q1r54s0m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "students_master",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("middle_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone_country_iso2", sa.String(length=2), nullable=True),
        sa.Column("phone_local", sa.String(length=20), nullable=True),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("phone_country_iso2_secondary", sa.String(length=2), nullable=True),
        sa.Column("phone_local_secondary", sa.String(length=20), nullable=True),
        sa.Column("phone_number_secondary", sa.String(length=50), nullable=True),
        sa.Column("address1", sa.String(length=255), nullable=True),
        sa.Column("address2", sa.String(length=255), nullable=True),
        sa.Column("address3", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("country_iso2", sa.String(length=2), nullable=True),
        sa.Column("zipcode", sa.String(length=20), nullable=True),
        sa.Column("degree_code", sa.String(length=50), nullable=True),
        sa.Column("degree_other", sa.String(length=255), nullable=True),
        sa.Column("major", sa.String(length=255), nullable=True),
        sa.Column("university", sa.String(length=255), nullable=True),
        sa.Column("graduation_year", sa.Integer(), nullable=True),
        sa.Column("gpa_cgpa_code", sa.String(length=50), nullable=True),
        sa.Column("gpa_cgpa_other", sa.String(length=255), nullable=True),
        sa.Column("target_destination_iso2", sa.String(length=2), nullable=True),
        sa.Column("target_program_code", sa.String(length=50), nullable=True),
        sa.Column("target_course_code", sa.String(length=50), nullable=True),
        sa.Column("english_test_scores", sa.String(length=100), nullable=True),
        sa.Column("gre_score", sa.String(length=50), nullable=True),
        sa.Column("gmat_score", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_students_master_id", "students_master", ["id"])
    op.create_index("ix_students_master_lead_id", "students_master", ["lead_id"], unique=True)
    op.create_index("ix_students_master_booking_id", "students_master", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_students_master_booking_id", table_name="students_master")
    op.drop_index("ix_students_master_lead_id", table_name="students_master")
    op.drop_index("ix_students_master_id", table_name="students_master")
    op.drop_table("students_master")
