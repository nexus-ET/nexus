"""add status_definitions and lead_status_history tables

Revision ID: l8h1i6j70k2f
Revises: k7g0h5i69j1e
Create Date: 2026-06-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l8h1i6j70k2f"
down_revision: Union[str, Sequence[str], None] = "k7g0h5i69j1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_status_history CASCADE")
    op.execute("DROP TABLE IF EXISTS status_definitions CASCADE")

    op.create_table(
        "status_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("next_stage_id", sa.Integer(), sa.ForeignKey("status_definitions.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_status_definitions_id", "status_definitions", ["id"])
    op.create_index("ix_status_definitions_stage_name", "status_definitions", ["stage_name"], unique=True)
    op.create_index("ix_status_definitions_category", "status_definitions", ["category"])
    op.create_index("ix_status_definitions_sort_order", "status_definitions", ["sort_order"])

    op.execute(
        """
        INSERT INTO status_definitions (id, stage_name, category, sort_order, description) VALUES
        (1, 'Lead: New', 'Lead', 10, 'Initial inquiry received and waiting for first contact.'),
        (2, 'Lead: Outreach', 'Lead', 20, 'First contact attempt initiated by advisor.'),
        (3, 'Lead: Engagement', 'Lead', 30, 'Student responded and active conversation started.'),
        (4, 'Lead: Cancelled (Not Interested)', 'Lead', 40, 'Student decided not to pursue services at this stage.'),
        (5, 'Lead: Deferred', 'Lead', 50, 'Student is interested but postponing their plans.'),
        (6, 'Counselling: Scheduled', 'Counselling', 60, 'Appointment date and time confirmed.'),
        (7, 'Counselling: Finished', 'Counselling', 70, 'Counselling session successfully completed.'),
        (8, 'Counselling: Prospect Qualified', 'Counselling', 80, 'Student meets criteria and is ready for application.'),
        (9, 'Counselling: Follow-up', 'Counselling', 90, 'Additional session required to clarify student needs.'),
        (10, 'Counselling: Cancelled (Not Interested)', 'Counselling', 100, 'Student withdrew during the counselling phase.'),
        (11, 'Counselling: Deferred', 'Counselling', 110, 'Counselling paused by student request.'),
        (12, 'Admission: Application Doc-Prep', 'Admission', 120, 'Gathering necessary documents for application.'),
        (13, 'Admission: Application Review', 'Admission', 130, 'Internal review of documents before submission.'),
        (14, 'Admission: Application Submitted', 'Admission', 140, 'Application officially sent to the university.'),
        (15, 'Admission: Application Assessment', 'Admission', 150, 'Awaiting university decision or entrance interview.'),
        (16, 'Admission: Application Accepted', 'Admission', 160, 'University has approved the application.'),
        (17, 'Admission: Offer Letter Received', 'Admission', 170, 'Official offer letter received and reviewed.'),
        (18, 'Admission: Application Rejected', 'Admission', 180, 'University declined the application.'),
        (19, 'Visa: Application Document Prep', 'Visa', 190, 'Preparing financial and immigration documents.'),
        (20, 'Visa: Application Filing', 'Visa', 200, 'Visa application submitted to authorities.'),
        (21, 'Visa: Application Processing', 'Visa', 210, 'Embassy or consulate is reviewing the file.'),
        (22, 'Visa: Biometrics/Interview', 'Visa', 220, 'Attending mandatory visa appointment/biometrics.'),
        (23, 'Visa: Application Approved', 'Visa', 230, 'Visa application has been granted.'),
        (24, 'Visa: Issued/Collected', 'Visa', 240, 'Visa stamped and passport retrieved.'),
        (25, 'Visa: Application Rejected', 'Visa', 250, 'Visa application was declined.'),
        (26, 'Pre-Departure: Orientation', 'Pre-Departure', 260, 'Attending pre-departure briefing session.'),
        (27, 'Pre-Departure: Travel/Insurance/ForEx', 'Pre-Departure', 270, 'Finalizing travel, insurance, and currency needs.'),
        (28, 'Pre-Departure: Accommodation', 'Pre-Departure', 280, 'Housing secured for arrival.'),
        (29, 'Pre-Departure: Final Documentation', 'Pre-Departure', 290, 'Completing final health and enrollment forms.'),
        (30, 'Pre-Departure: Travel Confirmed', 'Pre-Departure', 300, 'All travel logistics finalized and verified.'),
        (31, 'Arrival: Landed', 'Arrival', 310, 'Student has arrived in the target country.'),
        (32, 'Arrival: Campus Reporting', 'Arrival', 320, 'Student has reported to the university office.'),
        (33, 'Prospect: Enrolled & Closed', 'Prospect', 330, 'Student is successfully settled and attending.'),
        (34, 'Prospect: Cancelled & Closed', 'Prospect', 340, 'Process permanently terminated.'),
        (35, 'Prospect: Relaunch', 'Prospect', 350, 'Restarting process after a previous rejection or change.')
        """
    )
    op.execute("SELECT setval('status_definitions_id_seq', (SELECT MAX(id) FROM status_definitions))")
    op.execute(
        """
        UPDATE status_definitions SET next_stage_id = id + 1
        WHERE id IN (1, 2, 3, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 26, 27, 28, 29, 30, 31, 32)
        """
    )

    op.create_table(
        "lead_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "status_definition_id",
            sa.Integer(),
            sa.ForeignKey("status_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("counselling_bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("counsellor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_lead_status_history_id", "lead_status_history", ["id"])
    op.create_index("ix_lead_status_history_lead_id", "lead_status_history", ["lead_id"])
    op.create_index("ix_lead_status_history_status_definition_id", "lead_status_history", ["status_definition_id"])
    op.create_index("ix_lead_status_history_booking_id", "lead_status_history", ["booking_id"])
    op.create_index("ix_lead_status_history_created_at", "lead_status_history", ["created_at"])

    op.add_column("leads", sa.Column("status_definition_id", sa.Integer(), nullable=True))
    op.add_column("leads", sa.Column("status_entered_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_leads_status_definition_id",
        "leads",
        "status_definitions",
        ["status_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_leads_status_definition_id", "leads", ["status_definition_id"])

    op.execute(
        """
        UPDATE leads
        SET status_definition_id = CASE admission_stage
            WHEN 'COUNSELLING' THEN 6
            WHEN 'AWAITING_DOCS' THEN 12
            WHEN 'APPLIED' THEN 14
            WHEN 'UNDER_REVIEW' THEN 15
            WHEN 'OFFERED' THEN 17
            WHEN 'ENROLLED' THEN 33
            WHEN 'ARCHIVED' THEN 34
            ELSE 1
        END
        WHERE status_definition_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE leads
        SET status_entered_at = COALESCE(admission_stage_entered_at, created_at)
        WHERE status_entered_at IS NULL AND status_definition_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_leads_status_definition_id", table_name="leads")
    op.drop_constraint("fk_leads_status_definition_id", "leads", type_="foreignkey")
    op.drop_column("leads", "status_entered_at")
    op.drop_column("leads", "status_definition_id")

    op.drop_index("ix_lead_status_history_created_at", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_booking_id", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_status_definition_id", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_lead_id", table_name="lead_status_history")
    op.drop_index("ix_lead_status_history_id", table_name="lead_status_history")
    op.drop_table("lead_status_history")

    op.drop_index("ix_status_definitions_sort_order", table_name="status_definitions")
    op.drop_index("ix_status_definitions_category", table_name="status_definitions")
    op.drop_index("ix_status_definitions_stage_name", table_name="status_definitions")
    op.drop_index("ix_status_definitions_id", table_name="status_definitions")
    op.drop_table("status_definitions")
