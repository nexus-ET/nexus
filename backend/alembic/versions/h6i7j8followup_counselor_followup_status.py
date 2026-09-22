"""counselor_status_master + counselor_followup_logs

Revision ID: h6i7j8followup
Revises: g5h6i7leadact
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h6i7j8followup"
down_revision: Union[str, Sequence[str], None] = "g5h6i7leadact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_SEED = [
    (
        "callback_scheduled",
        "Callback Scheduled",
        "Points Discussed: Discussed country preferences and budget constraints. "
        "Action Items: Call back on [Date] at [Time] with shortlisted university options.",
    ),
    (
        "walkin_scheduled_completed",
        "Walk-in Scheduled / Completed",
        "Points Discussed: Student visited the office. Covered course options, eligibility criteria, "
        "and documentation checklist. Action Items: Follow up regarding missing transcripts.",
    ),
    (
        "not_answered_unresponsive",
        "Not Answered / Unresponsive",
        "Points Discussed: Attempted phone call/WhatsApp message. No response received from the student. "
        "Action Items: Schedule an automated follow-up ping after 48 hours.",
    ),
    (
        "application_registered",
        "Application Registered",
        "Points Discussed: Student agreed to move forward and registered their profile. "
        "Action Items: Collect initial application documents and initiate ScanX verification.",
    ),
    (
        "hot_prospect",
        "Hot Prospect / High Intent",
        "Points Discussed: Highly engaged student ready to make a final university selection soon. "
        "Action Items: Send tailored university comparison sheet.",
    ),
    (
        "more_information_requested",
        "More Information Requested",
        "Points Discussed: Student asked for specific details regarding tuition fees, living costs, "
        "or scholarship options. Action Items: Email detailed fee breakdown and financial aid guide.",
    ),
    (
        "cold_lead_lost_interest",
        "Cold Lead / Lost Interest",
        "Points Discussed: Student is currently considering other options or postponing plans. "
        "Action Items: Place in long-term nurture drip campaign.",
    ),
    (
        "future_intake_deferred",
        "Future Intake (Deferred)",
        "Points Discussed: Student intends to apply for a later intake cycle. "
        "Action Items: Set reminder to re-engage 6 months prior to target intake.",
    ),
    (
        "visa_counseling_doc_review",
        "Visa Counseling / Doc Review",
        "Points Discussed: Reviewed visa requirements, financial proof guidelines, and passport details "
        "via ScanX. Action Items: Verify supporting financial affidavits.",
    ),
    (
        "parent_consulted",
        "Parent Consulted",
        "Points Discussed: Spoke with parents/guardians regarding financial budgeting and destination safety. "
        "Action Items: Address parental concerns via email summary.",
    ),
]


def upgrade() -> None:
    op.create_table(
        "counselor_status_master",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status_key", sa.String(length=80), nullable=False),
        sa.Column("status_heading", sa.String(length=160), nullable=False),
        sa.Column("default_description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint("status_key", name="uq_counselor_status_master_status_key"),
    )
    op.create_index(
        "ix_counselor_status_master_status_key",
        "counselor_status_master",
        ["status_key"],
        unique=True,
    )
    op.create_index(
        "ix_counselor_status_master_is_active",
        "counselor_status_master",
        ["is_active"],
    )

    seed_table = sa.table(
        "counselor_status_master",
        sa.column("status_key", sa.String),
        sa.column("status_heading", sa.String),
        sa.column("default_description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        seed_table,
        [
            {
                "status_key": key,
                "status_heading": heading,
                "default_description": description,
                "is_active": True,
                "sort_order": index + 1,
            }
            for index, (key, heading, description) in enumerate(STATUS_SEED)
        ],
    )

    op.create_table(
        "counselor_followup_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("counselor_id", sa.String(length=255), nullable=True),
        sa.Column("status_id", sa.Integer(), nullable=False),
        sa.Column("points_discussed", sa.Text(), nullable=False),
        sa.Column("action_items", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name="fk_counselor_followup_logs_lead_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["status_id"],
            ["counselor_status_master.id"],
            name="fk_counselor_followup_logs_status_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_counselor_followup_logs_lead_id",
        "counselor_followup_logs",
        ["lead_id"],
    )
    op.create_index(
        "ix_counselor_followup_logs_status_id",
        "counselor_followup_logs",
        ["status_id"],
    )
    op.create_index(
        "ix_counselor_followup_logs_created_at",
        "counselor_followup_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_counselor_followup_logs_created_at", table_name="counselor_followup_logs")
    op.drop_index("ix_counselor_followup_logs_status_id", table_name="counselor_followup_logs")
    op.drop_index("ix_counselor_followup_logs_lead_id", table_name="counselor_followup_logs")
    op.drop_table("counselor_followup_logs")
    op.drop_index("ix_counselor_status_master_is_active", table_name="counselor_status_master")
    op.drop_index("ix_counselor_status_master_status_key", table_name="counselor_status_master")
    op.drop_table("counselor_status_master")
