"""FlowX pathway registry and rich application fields on enrollments.

Revision ID: aa1b2cflowxappform
Revises: z9a2b5flowxapps
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "aa1b2cflowxappform"
down_revision: Union[str, Sequence[str], None] = "z9a2b5flowxapps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PATHWAY_SEEDS = [
    ("centralized_national_portal", "Common App"),
    ("centralized_national_portal", "Coalition Application"),
    ("centralized_national_portal", "UCAS"),
    ("centralized_national_portal", "Studielink"),
    ("centralized_national_portal", "OUAC"),
    ("centralized_national_portal", "CAO"),
    ("centralized_national_portal", "VTAC"),
    ("centralized_national_portal", "UAC"),
    ("regional_clearing_agency", "uni-assist"),
    ("regional_clearing_agency", "LSAC"),
    ("regional_clearing_agency", "CAS"),
    ("third_party_aggregator", "ApplyBoard"),
    ("third_party_aggregator", "Adventus"),
    ("third_party_aggregator", "Course Finder"),
    ("third_party_aggregator", "Studyportals"),
    ("direct_institutional_portal", "Direct Institutional Portal"),
    ("partner_portal", "Partner Portal"),
    ("paper_offline_route", "Paper / Offline Route"),
]


def upgrade() -> None:
    op.create_table(
        "flowx_pathway_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("pathway_type", sa.String(64), nullable=False),
        sa.Column("pathway_name", sa.String(255), nullable=False),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("pathway_name", name="uq_flowx_pathway_registry_name"),
    )
    op.create_index("idx_flowx_pathway_type", "flowx_pathway_registry", ["pathway_type"])

    pathway_table = sa.table(
        "flowx_pathway_registry",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("pathway_type", sa.String),
        sa.column("pathway_name", sa.String),
        sa.column("is_custom", sa.Boolean),
    )
    import uuid

    op.bulk_insert(
        pathway_table,
        [
            {
                "id": str(uuid.uuid4()),
                "pathway_type": ptype,
                "pathway_name": pname,
                "is_custom": False,
            }
            for ptype, pname in PATHWAY_SEEDS
        ],
    )

    op.add_column("flowx_enrollments", sa.Column("university_name", sa.String(255), nullable=True))
    op.add_column(
        "flowx_enrollments",
        sa.Column("campus_id", sa.Integer(), sa.ForeignKey("campuses.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "flowx_enrollments",
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("levels.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "flowx_enrollments",
        sa.Column(
            "qualification_program_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "flowx_enrollments",
        sa.Column(
            "intake_id",
            sa.Integer(),
            sa.ForeignKey("institution_intakes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("flowx_enrollments", sa.Column("pathway_type", sa.String(64), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("pathway_name", sa.String(255), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("portal_url", sa.Text(), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("portal_username", sa.String(255), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("portal_password_hint", sa.Text(), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("institutional_app_id", sa.String(255), nullable=True))
    op.add_column(
        "flowx_enrollments",
        sa.Column("application_status", sa.String(64), nullable=False, server_default="drafting"),
    )
    op.add_column(
        "flowx_enrollments",
        sa.Column("fee_status", sa.String(64), nullable=False, server_default="not_required"),
    )
    op.add_column("flowx_enrollments", sa.Column("fee_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "flowx_enrollments",
        sa.Column("fee_currency", sa.String(10), nullable=False, server_default="USD"),
    )
    op.add_column("flowx_enrollments", sa.Column("internal_target_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("official_deadline", sa.DateTime(timezone=True), nullable=True))
    op.add_column("flowx_enrollments", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("idx_flowx_enrollments_campus", "flowx_enrollments", ["campus_id"])
    op.create_index("idx_flowx_enrollments_intake", "flowx_enrollments", ["intake_id"])
    op.create_index("idx_flowx_enrollments_program", "flowx_enrollments", ["qualification_program_id"])
    op.create_index("idx_flowx_enrollments_app_status", "flowx_enrollments", ["application_status"])

    # Refine uniqueness: lead × country × college × intake
    op.execute("DROP INDEX IF EXISTS uq_flowx_enrollment_application")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_flowx_enrollment_application
        ON flowx_enrollments (
            lead_id,
            country_workflow_id,
            (COALESCE(college_id, 0)),
            (COALESCE(intake_id, 0))
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_flowx_enrollment_application")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_flowx_enrollment_application
        ON flowx_enrollments (lead_id, country_workflow_id, (COALESCE(college_id, 0)))
        """
    )
    for name in (
        "idx_flowx_enrollments_app_status",
        "idx_flowx_enrollments_program",
        "idx_flowx_enrollments_intake",
        "idx_flowx_enrollments_campus",
    ):
        op.drop_index(name, table_name="flowx_enrollments")
    for col in (
        "submitted_at",
        "official_deadline",
        "internal_target_date",
        "fee_currency",
        "fee_amount",
        "fee_status",
        "application_status",
        "institutional_app_id",
        "portal_password_hint",
        "portal_username",
        "portal_url",
        "pathway_name",
        "pathway_type",
        "intake_id",
        "qualification_program_id",
        "level_id",
        "campus_id",
        "university_name",
    ):
        op.drop_column("flowx_enrollments", col)
    op.drop_index("idx_flowx_pathway_type", table_name="flowx_pathway_registry")
    op.drop_table("flowx_pathway_registry")
