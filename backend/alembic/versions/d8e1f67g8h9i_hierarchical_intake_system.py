"""Hierarchical intake system: entity scoping, overrides, reminder fields.

Revision ID: d8e1f67g8h9i
Revises: c7d0e56f7g8h
Create Date: 2026-07-11 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e1f67g8h9i"
down_revision: Union[str, Sequence[str], None] = "c7d0e56f7g8h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "institution_intakes",
        sa.Column("entity_type", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("entity_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("is_overridden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("check_in_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("orientation_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "institution_intakes",
        sa.Column("class_start_date", sa.Date(), nullable=True),
    )

    bind.execute(
        sa.text(
            """
            UPDATE institution_intakes
            SET entity_type = CASE
                    WHEN campus_id IS NOT NULL THEN 'campus'
                    ELSE 'institution'
                END,
                entity_id = COALESCE(campus_id, institution_id),
                class_start_date = COALESCE(class_start_date, start_date)
            """
        )
    )

    op.create_index(
        "ix_institution_intakes_entity",
        "institution_intakes",
        ["entity_type", "entity_id"],
    )

    op.create_table(
        "calendar_intake_alert_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("term_name", sa.String(length=120), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(length=40), nullable=False, server_default="missing_intake"),
        sa.Column("alerted_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "institution_id",
            "entity_type",
            "entity_id",
            "term_name",
            "year",
            "alert_type",
            name="uq_calendar_intake_alert_scope",
        ),
    )
    op.create_index(
        "ix_calendar_intake_alert_logs_institution_id",
        "calendar_intake_alert_logs",
        ["institution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_intake_alert_logs_institution_id", table_name="calendar_intake_alert_logs")
    op.drop_table("calendar_intake_alert_logs")
    op.drop_index("ix_institution_intakes_entity", table_name="institution_intakes")
    op.drop_column("institution_intakes", "class_start_date")
    op.drop_column("institution_intakes", "orientation_date")
    op.drop_column("institution_intakes", "check_in_date")
    op.drop_column("institution_intakes", "is_overridden")
    op.drop_column("institution_intakes", "entity_id")
    op.drop_column("institution_intakes", "entity_type")
