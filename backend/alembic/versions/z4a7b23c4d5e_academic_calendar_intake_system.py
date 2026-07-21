"""Academic calendar and intake management system.

Revision ID: z4a7b23c4d5e
Revises: y3z6a22b3c4d
Create Date: 2026-07-10 14:00:00.000000
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "z4a7b23c4d5e"
down_revision: Union[str, Sequence[str], None] = "y3z6a22b3c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JsonColumn = sa.JSON().with_variant(postgresql.JSONB, "postgresql")

DEFAULT_TEMPLATES = [
    {
        "name": "Semester System",
        "description": "Two primary terms per academic year (Fall and Spring).",
        "sort_order": 1,
        "default_intake_configs": [
            {"term_name": "Fall", "intake_type": "Fixed", "expected_duration_months": 4},
            {"term_name": "Spring", "intake_type": "Fixed", "expected_duration_months": 4},
        ],
    },
    {
        "name": "Trimester System",
        "description": "Three terms per academic year.",
        "sort_order": 2,
        "default_intake_configs": [
            {"term_name": "Fall", "intake_type": "Fixed", "expected_duration_months": 3},
            {"term_name": "Winter", "intake_type": "Fixed", "expected_duration_months": 3},
            {"term_name": "Spring", "intake_type": "Fixed", "expected_duration_months": 3},
        ],
    },
    {
        "name": "Quarter System",
        "description": "Four quarters per academic year.",
        "sort_order": 3,
        "default_intake_configs": [
            {"term_name": "Q1", "intake_type": "Fixed", "expected_duration_months": 3},
            {"term_name": "Q2", "intake_type": "Fixed", "expected_duration_months": 3},
            {"term_name": "Q3", "intake_type": "Fixed", "expected_duration_months": 3},
            {"term_name": "Q4", "intake_type": "Fixed", "expected_duration_months": 3},
        ],
    },
    {
        "name": "Rolling Admissions",
        "description": "Continuous intake with optional end dates.",
        "sort_order": 4,
        "default_intake_configs": [
            {"term_name": "Rolling", "intake_type": "Rolling", "expected_duration_months": 12},
        ],
    },
]


def upgrade() -> None:
    op.create_table(
        "global_academic_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_intake_configs", JsonColumn, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_global_academic_templates_name", "global_academic_templates", ["name"])

    op.add_column(
        "institution_intakes",
        sa.Column("template_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("parent_intake_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("term_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column(
            "intake_type",
            sa.String(length=20),
            nullable=False,
            server_default="Fixed",
        ),
    )
    op.add_column(
        "institution_intakes",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="Draft",
        ),
    )

    op.create_foreign_key(
        "fk_institution_intakes_template_id",
        "institution_intakes",
        "global_academic_templates",
        ["template_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_institution_intakes_parent_intake_id",
        "institution_intakes",
        "institution_intakes",
        ["parent_intake_id"],
        ["id"],
    )
    op.create_index("ix_institution_intakes_year", "institution_intakes", ["year"])
    op.create_index("ix_institution_intakes_status", "institution_intakes", ["status"])

    op.execute(
        sa.text(
            """
            UPDATE institution_intakes
            SET term_name = name,
                year = COALESCE(EXTRACT(YEAR FROM start_date)::int, EXTRACT(YEAR FROM CURRENT_DATE)::int),
                intake_type = 'Fixed',
                status = CASE WHEN is_active THEN 'Open' ELSE 'Closed' END
            WHERE term_name IS NULL
            """
        )
    )

    op.create_table(
        "program_intake_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_intake_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["institution_intake_id"], ["institution_intakes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "institution_intake_id", name="uq_program_intake"),
    )
    op.create_index(
        "ix_program_intake_assignments_program_id",
        "program_intake_assignments",
        ["program_id"],
    )
    op.create_index(
        "ix_program_intake_assignments_institution_intake_id",
        "program_intake_assignments",
        ["institution_intake_id"],
    )

    templates = sa.table(
        "global_academic_templates",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("default_intake_configs", JsonColumn),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        templates,
        [
            {
                "name": item["name"],
                "description": item["description"],
                "default_intake_configs": item["default_intake_configs"],
                "sort_order": item["sort_order"],
            }
            for item in DEFAULT_TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_program_intake_assignments_institution_intake_id", table_name="program_intake_assignments")
    op.drop_index("ix_program_intake_assignments_program_id", table_name="program_intake_assignments")
    op.drop_table("program_intake_assignments")

    op.drop_index("ix_institution_intakes_status", table_name="institution_intakes")
    op.drop_index("ix_institution_intakes_year", table_name="institution_intakes")
    op.drop_constraint("fk_institution_intakes_parent_intake_id", "institution_intakes", type_="foreignkey")
    op.drop_constraint("fk_institution_intakes_template_id", "institution_intakes", type_="foreignkey")
    op.drop_column("institution_intakes", "status")
    op.drop_column("institution_intakes", "intake_type")
    op.drop_column("institution_intakes", "year")
    op.drop_column("institution_intakes", "term_name")
    op.drop_column("institution_intakes", "parent_intake_id")
    op.drop_column("institution_intakes", "template_id")

    op.drop_index("ix_global_academic_templates_name", table_name="global_academic_templates")
    op.drop_table("global_academic_templates")
