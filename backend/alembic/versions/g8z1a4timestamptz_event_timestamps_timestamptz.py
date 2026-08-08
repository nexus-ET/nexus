"""Convert event timestamps to TIMESTAMPTZ (UTC).

Revision ID: g8z1a4timestamptz
Revises: f7y0d3esolution
Create Date: 2026-07-27 06:40:00.000000

Existing TIMESTAMP WITHOUT TIME ZONE values are interpreted as UTC.
Business-local wall-clock columns are intentionally left unchanged:
  - counselling_bookings.scheduled_time
  - leads.consultation_scheduled_at
  - audit_logs.created_at (business_now)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g8z1a4timestamptz"
down_revision: Union[str, Sequence[str], None] = "f7y0d3esolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) — event instants only
EVENT_TIMESTAMP_COLUMNS: list[tuple[str, str]] = [
    # Messaging
    ("messages", "created_at"),
    ("message_history", "created_at"),
    ("processed_messages", "created_at"),
    ("message_reactions", "created_at"),
    ("conversations", "created_at"),
    ("conversations", "last_message_at"),
    ("conversation_participants", "joined_at"),
    ("conversation_participants", "last_read_at"),
    ("conversation_audit_logs", "created_at"),
    ("internal_messages", "created_at"),
    ("team_chat_messages", "created_at"),
    ("team_chat_messages", "read_at"),
    ("notification_logs", "sent_at"),
    # Leads / pipeline
    ("leads", "created_at"),
    ("leads", "updated_at"),
    ("leads", "archived_at"),
    ("leads", "status_entered_at"),
    ("leads", "admission_stage_entered_at"),
    ("leads", "documents_submitted_at"),
    ("raw_incoming_leads", "received_at"),
    ("raw_incoming_leads", "processed_at"),
    ("raw_incoming_leads", "created_at"),
    ("lead_quarantine", "created_at"),
    ("lead_quarantine", "updated_at"),
    ("lead_quarantine", "reprocessed_at"),
    ("status_history", "created_at"),
    ("admission_history", "created_at"),
    # Counselling events (not scheduled_time)
    ("counselling_bookings", "created_at"),
    ("counselling_bookings", "updated_at"),
    ("counselling_bookings", "completed_at"),
    ("counselling_notes", "created_at"),
    ("counselling_notes", "updated_at"),
    ("consultation_slots", "created_at"),
    ("candidate_tasks", "created_at"),
    ("candidate_tasks", "completed_at"),
    # Ops
    ("exception_logs", "attempt_timestamp"),
    ("exception_logs", "created_at"),
    ("exception_logs", "resolved_at"),
    ("sync_logs", "started_at"),
    ("sync_logs", "attempt_timestamp"),
    ("sync_logs", "completed_at"),
    ("sync_logs", "created_at"),
    ("security_audit_runs", "started_at"),
    ("security_audit_runs", "completed_at"),
    ("security_audit_runs", "created_at"),
    ("system_logs", "created_at"),
    ("calendar_intake_alert_logs", "alerted_at"),
    ("agent_configs", "updated_at"),
    ("dynamic_settings", "updated_at"),
    # Users / org
    ("users", "creation_date"),
    ("users", "activation_date"),
    ("users", "deactivation_date"),
    ("businesses", "created_at"),
    ("businesses", "updated_at"),
    ("students_master", "created_at"),
    ("students_master", "updated_at"),
    # Matching / profile
    ("institutions", "created_at"),
    ("institutions", "updated_at"),
    ("institution_wizard_drafts", "created_at"),
    ("institution_wizard_drafts", "updated_at"),
    ("academia_audit_logs", "created_at"),
    ("matching_weight_profiles", "created_at"),
    ("matching_weight_profiles", "updated_at"),
    ("matching_shortlist_runs", "created_at"),
    ("matching_shortlist_items", "created_at"),
    ("candidate_educations", "created_at"),
    ("candidate_educations", "updated_at"),
    ("candidate_test_scores", "created_at"),
    ("work_experiences", "created_at"),
    ("research_projects", "created_at"),
    ("research_projects", "updated_at"),
    ("non_academic_activities", "created_at"),
    ("non_academic_activities", "updated_at"),
    ("digital_presence_links", "created_at"),
    ("digital_presence_links", "updated_at"),
    ("course_education_major_mappings", "created_at"),
    ("program_education_major_mappings", "created_at"),
    ("public_holidays", "created_at"),
    ("public_holidays", "updated_at"),
]


def _column_udt(bind, table: str, column: str) -> str | None:
    row = bind.execute(
        sa.text(
            """
            SELECT c.udt_name
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = :table
              AND c.column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row[0] if row else None


def upgrade() -> None:
    bind = op.get_bind()
    for table, column in EVENT_TIMESTAMP_COLUMNS:
        udt = _column_udt(bind, table, column)
        if udt is None:
            continue
        if udt == "timestamptz":
            continue
        if udt not in {"timestamp", "timestamptz"}:
            # unexpected type — skip rather than fail the whole release
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" '
                f'ALTER COLUMN "{column}" '
                f"TYPE TIMESTAMPTZ USING \"{column}\" AT TIME ZONE 'UTC'"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in reversed(EVENT_TIMESTAMP_COLUMNS):
        udt = _column_udt(bind, table, column)
        if udt != "timestamptz":
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" '
                f'ALTER COLUMN "{column}" '
                f"TYPE TIMESTAMP WITHOUT TIME ZONE "
                f"USING \"{column}\" AT TIME ZONE 'UTC'"
            )
        )
