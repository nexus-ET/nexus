"""add institution wizard drafts, intakes, pictures, offerings, academia audit

Revision ID: f4g7h0i13j5e
Revises: e3f6g9h02i4d
Create Date: 2026-07-08 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4g7h0i13j5e"
down_revision: Union[str, Sequence[str], None] = "e3f6g9h02i4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institution_wizard_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Untitled Institution"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_steps", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_institution_wizard_drafts_id", "institution_wizard_drafts", ["id"])
    op.create_index(
        "ix_institution_wizard_drafts_created_by_user_id",
        "institution_wizard_drafts",
        ["created_by_user_id"],
    )
    op.create_index(
        "ix_institution_wizard_drafts_institution_id",
        "institution_wizard_drafts",
        ["institution_id"],
    )
    op.create_index("ix_institution_wizard_drafts_status", "institution_wizard_drafts", ["status"])

    op.create_table(
        "institution_intakes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("intake_code", sa.String(length=50), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("application_deadline", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_institution_intakes_institution_id", "institution_intakes", ["institution_id"])

    op.create_table(
        "institution_pictures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("caption", sa.String(length=255), nullable=True),
        sa.Column("picture_type", sa.String(length=40), nullable=False, server_default="gallery"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_institution_pictures_institution_id", "institution_pictures", ["institution_id"])

    op.create_table(
        "institution_course_offerings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id"), nullable=True),
        sa.Column("college_id", sa.Integer(), sa.ForeignKey("colleges.id"), nullable=True),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("target_courses.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index(
        "ix_institution_course_offerings_institution_id",
        "institution_course_offerings",
        ["institution_id"],
    )

    op.create_table(
        "academia_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("old_data", postgresql.JSONB(), nullable=True),
        sa.Column("new_data", postgresql.JSONB(), nullable=True),
        sa.Column("rollback_of_id", sa.Integer(), sa.ForeignKey("academia_audit_logs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_academia_audit_logs_entity_type", "academia_audit_logs", ["entity_type"])
    op.create_index("ix_academia_audit_logs_entity_id", "academia_audit_logs", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_academia_audit_logs_entity_id", table_name="academia_audit_logs")
    op.drop_index("ix_academia_audit_logs_entity_type", table_name="academia_audit_logs")
    op.drop_table("academia_audit_logs")

    op.drop_index("ix_institution_course_offerings_institution_id", table_name="institution_course_offerings")
    op.drop_table("institution_course_offerings")

    op.drop_index("ix_institution_pictures_institution_id", table_name="institution_pictures")
    op.drop_table("institution_pictures")

    op.drop_index("ix_institution_intakes_institution_id", table_name="institution_intakes")
    op.drop_table("institution_intakes")

    op.drop_index("ix_institution_wizard_drafts_status", table_name="institution_wizard_drafts")
    op.drop_index("ix_institution_wizard_drafts_institution_id", table_name="institution_wizard_drafts")
    op.drop_index("ix_institution_wizard_drafts_created_by_user_id", table_name="institution_wizard_drafts")
    op.drop_index("ix_institution_wizard_drafts_id", table_name="institution_wizard_drafts")
    op.drop_table("institution_wizard_drafts")
