"""add phase1 university matching tables

Revision ID: d5e8f1a64h7i
Revises: c4d7e0f53g6h
Create Date: 2026-07-22 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d5e8f1a64h7i"
down_revision: Union[str, Sequence[str], None] = "c4d7e0f53g6h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "matching_weight_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight_academic", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_profile", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_aspirations", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight_safety", sa.Numeric(5, 4), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_matching_weight_profiles_id", "matching_weight_profiles", ["id"])
    op.create_index("ix_matching_weight_profiles_code", "matching_weight_profiles", ["code"], unique=True)

    op.create_table(
        "matching_shortlist_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "students_master_id",
            sa.Integer(),
            sa.ForeignKey("students_master.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "weight_profile_id",
            sa.Integer(),
            sa.ForeignKey("matching_weight_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("algorithm_version", sa.String(length=40), nullable=False, server_default="phase1-v1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column(
            "classification_mode",
            sa.String(length=40),
            nullable=False,
            server_default="heuristic_fit",
        ),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_snapshot", JsonType, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_matching_shortlist_runs_id", "matching_shortlist_runs", ["id"])
    op.create_index("ix_matching_shortlist_runs_lead_id", "matching_shortlist_runs", ["lead_id"])
    op.create_index("ix_matching_shortlist_runs_booking_id", "matching_shortlist_runs", ["booking_id"])
    op.create_index(
        "ix_matching_shortlist_runs_students_master_id",
        "matching_shortlist_runs",
        ["students_master_id"],
    )
    op.create_index(
        "ix_matching_shortlist_runs_weight_profile_id",
        "matching_shortlist_runs",
        ["weight_profile_id"],
    )
    op.create_index(
        "ix_matching_shortlist_runs_algorithm_version",
        "matching_shortlist_runs",
        ["algorithm_version"],
    )
    op.create_index("ix_matching_shortlist_runs_status", "matching_shortlist_runs", ["status"])
    op.create_index("ix_matching_shortlist_runs_created_at", "matching_shortlist_runs", ["created_at"])

    op.create_table(
        "matching_shortlist_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("matching_shortlist_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.Integer(),
            sa.ForeignKey("institutions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "offering_id",
            sa.Integer(),
            sa.ForeignKey("institution_course_offerings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consolidated_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("s_academic", sa.Numeric(6, 2), nullable=False),
        sa.Column("s_profile", sa.Numeric(6, 2), nullable=False),
        sa.Column("s_aspirations", sa.Numeric(6, 2), nullable=False),
        sa.Column("s_safety", sa.Numeric(6, 2), nullable=False),
        sa.Column("fit_band", sa.String(length=20), nullable=False),
        sa.Column("explanation", JsonType, nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "institution_id",
            "offering_id",
            name="uq_shortlist_run_inst_offering",
        ),
    )
    op.create_index("ix_matching_shortlist_items_id", "matching_shortlist_items", ["id"])
    op.create_index("ix_matching_shortlist_items_run_id", "matching_shortlist_items", ["run_id"])
    op.create_index(
        "ix_matching_shortlist_items_institution_id",
        "matching_shortlist_items",
        ["institution_id"],
    )
    op.create_index(
        "ix_matching_shortlist_items_offering_id",
        "matching_shortlist_items",
        ["offering_id"],
    )
    op.create_index("ix_matching_shortlist_items_rank", "matching_shortlist_items", ["rank"])
    op.create_index("ix_matching_shortlist_items_fit_band", "matching_shortlist_items", ["fit_band"])

    weight_profiles = sa.table(
        "matching_weight_profiles",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("weight_academic", sa.Numeric),
        sa.column("weight_profile", sa.Numeric),
        sa.column("weight_aspirations", sa.Numeric),
        sa.column("weight_safety", sa.Numeric),
        sa.column("is_default", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        weight_profiles,
        [
            {
                "code": "default",
                "name": "Default (balanced)",
                "description": "Phase 1 balanced weights for general master's shortlists.",
                "weight_academic": "0.3500",
                "weight_profile": "0.2500",
                "weight_aspirations": "0.3000",
                "weight_safety": "0.1000",
                "is_default": True,
                "is_active": True,
            },
            {
                "code": "research_masters",
                "name": "Research master's",
                "description": "Higher weight on profile/research strength for research-oriented programs.",
                "weight_academic": "0.3500",
                "weight_profile": "0.4000",
                "weight_aspirations": "0.1500",
                "weight_safety": "0.1000",
                "is_default": False,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("matching_shortlist_items")
    op.drop_table("matching_shortlist_runs")
    op.drop_table("matching_weight_profiles")
