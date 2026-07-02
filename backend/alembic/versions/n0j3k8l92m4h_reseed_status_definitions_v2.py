"""reseed status_definitions v2 (39 stages)

Revision ID: n0j3k8l92m4h
Revises: m9i2j7k81l3g
Create Date: 2026-06-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "n0j3k8l92m4h"
down_revision: Union[str, Sequence[str], None] = "m9i2j7k81l3g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TO_NEW_STATUS_ID: dict[int, int] = {
    1: 1,
    2: 2,
    3: 3,
    4: 8,
    5: 9,
    6: 10,
    7: 11,
    8: 12,
    9: 13,
    10: 14,
    11: 15,
    12: 16,
    13: 17,
    14: 18,
    15: 19,
    16: 20,
    17: 21,
    18: 22,
    19: 23,
    20: 24,
    21: 25,
    22: 26,
    23: 27,
    24: 28,
    25: 29,
    26: 30,
    27: 31,
    28: 32,
    29: 33,
    30: 34,
    31: 35,
    32: 36,
    33: 37,
    34: 38,
    35: 39,
}


def _remap_status_ids() -> None:
    case_parts = [f"WHEN {old} THEN {new}" for old, new in OLD_TO_NEW_STATUS_ID.items()]
    case_sql = " ".join(case_parts)
    op.execute(
        f"""
        UPDATE leads
        SET status_definition_id = CASE status_definition_id
            {case_sql}
            ELSE status_definition_id
        END
        WHERE status_definition_id IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE lead_status_history
        SET status_definition_id = CASE status_definition_id
            {case_sql}
            ELSE status_definition_id
        END
        """
    )


def upgrade() -> None:
    _remap_status_ids()

    op.execute("ALTER TABLE leads DROP CONSTRAINT IF EXISTS fk_leads_status_definition_id")
    op.execute(
        "ALTER TABLE lead_status_history DROP CONSTRAINT IF EXISTS lead_status_history_status_definition_id_fkey"
    )
    op.execute("DROP TABLE IF EXISTS status_definitions CASCADE")

    op.execute(
        """
        CREATE TABLE status_definitions (
            id SERIAL PRIMARY KEY,
            stage_name VARCHAR(120) NOT NULL UNIQUE,
            category VARCHAR(50) NOT NULL,
            description TEXT,
            next_stage_id INT REFERENCES status_definitions(id) ON DELETE SET NULL
        )
        """
    )
    op.execute("CREATE INDEX ix_status_definitions_id ON status_definitions (id)")
    op.execute("CREATE UNIQUE INDEX ix_status_definitions_stage_name ON status_definitions (stage_name)")
    op.execute("CREATE INDEX ix_status_definitions_category ON status_definitions (category)")

    op.execute(
        """
        INSERT INTO status_definitions (id, stage_name, category, description) VALUES
        (1, 'Lead: New', 'Lead', 'Initial inquiry received, pending first contact.'),
        (2, 'Lead: Outreach', 'Lead', 'First outreach attempt initiated by advisor.'),
        (3, 'Lead: Engagement', 'Lead', 'Active conversation established with the student.'),
        (4, 'Lead: Session Booked', 'Lead', 'Counselling session confirmed via WhatsApp.'),
        (5, 'Lead: Session Rescheduled', 'Lead', 'Student requested a change to the meeting time.'),
        (6, 'Lead: Session Cancelled', 'Lead', 'Student cancelled the initial meeting request.'),
        (7, 'Lead: Cancelled (No Answer)', 'Lead', 'Unresponsive after multiple outreach attempts.'),
        (8, 'Lead: Cancelled (Not Interested)', 'Lead', 'Student decided not to pursue services.'),
        (9, 'Lead: Deferred', 'Lead', 'Interested but postponing plans to a later date.'),
        (10, 'Counselling: Scheduled', 'Counselling', 'Appointment date and time finalized.'),
        (11, 'Counselling: Finished', 'Counselling', 'Counselling session successfully completed.'),
        (12, 'Counselling: Prospect Qualified', 'Counselling', 'Student meets criteria, moving to application.'),
        (13, 'Counselling: Follow-up', 'Counselling', 'Additional session needed for clarity.'),
        (14, 'Counselling: Cancelled (Not Interested)', 'Counselling', 'Withdrew during the counselling phase.'),
        (15, 'Counselling: Deferred', 'Counselling', 'Counselling process paused by student request.'),
        (16, 'Admission: Application Doc-Prep', 'Admission', 'Gathering necessary documents for submission.'),
        (17, 'Admission: Application Review', 'Admission', 'Internal review of documentation for accuracy.'),
        (18, 'Admission: Application Submitted', 'Admission', 'Application sent to the university.'),
        (19, 'Admission: Application Assessment', 'Admission', 'Awaiting university decision or interview.'),
        (20, 'Admission: Application Accepted', 'Admission', 'University approval confirmed.'),
        (21, 'Admission: Offer Letter Received', 'Admission', 'Official offer letter received and processed.'),
        (22, 'Admission: Application Rejected', 'Admission', 'University declined the application.'),
        (23, 'Visa: Application Document Prep', 'Visa', 'Preparing financial and immigration evidence.'),
        (24, 'Visa: Application Filing', 'Visa', 'Application submitted to visa authorities.'),
        (25, 'Visa: Application Processing', 'Visa', 'Embassy is currently reviewing the file.'),
        (26, 'Visa: Biometrics/Interview', 'Visa', 'Attending mandatory biometric appointment.'),
        (27, 'Visa: Application Approved', 'Visa', 'Visa application has been granted.'),
        (28, 'Visa: Issued/Collected', 'Visa', 'Visa stamped and passport retrieved.'),
        (29, 'Visa: Application Rejected', 'Visa', 'Visa application was declined.'),
        (30, 'Pre-Departure: Orientation', 'Pre-Departure', 'Attending pre-departure briefing.'),
        (31, 'Pre-Departure: Travel/Insurance/ForEx', 'Pre-Departure', 'Finalizing travel, insurance, and currency.'),
        (32, 'Pre-Departure: Accommodation', 'Pre-Departure', 'Housing secured for arrival.'),
        (33, 'Pre-Departure: Final Documentation', 'Pre-Departure', 'Completing final health/enrollment forms.'),
        (34, 'Pre-Departure: Travel Confirmed', 'Pre-Departure', 'All travel logistics verified.'),
        (35, 'Arrival: Landed', 'Arrival', 'Student arrived in target country.'),
        (36, 'Arrival: Campus Reporting', 'Arrival', 'Reported to the university office.'),
        (37, 'Prospect: Enrolled & Closed', 'Prospect', 'Successfully enrolled and settled.'),
        (38, 'Prospect: Cancelled & Closed', 'Prospect', 'Process permanently terminated.'),
        (39, 'Prospect: Relaunch', 'Prospect', 'Restarting process after change/rejection.')
        """
    )
    op.execute("SELECT setval('status_definitions_id_seq', (SELECT MAX(id) FROM status_definitions))")

    op.execute(
        "UPDATE status_definitions SET next_stage_id = id + 1 "
        "WHERE id IN (1, 2, 3, 10, 11, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 30, 31, 32, 33, 35)"
    )
    op.execute("UPDATE status_definitions SET next_stage_id = 10 WHERE id IN (4, 5, 13)")
    op.execute("UPDATE status_definitions SET next_stage_id = 16 WHERE id = 12")
    op.execute("UPDATE status_definitions SET next_stage_id = 23 WHERE id = 21")
    op.execute("UPDATE status_definitions SET next_stage_id = 35 WHERE id = 34")
    op.execute(
        "UPDATE status_definitions SET next_stage_id = NULL "
        "WHERE id IN (6, 7, 8, 9, 14, 15, 22, 29, 37, 38, 39)"
    )

    op.execute(
        """
        ALTER TABLE leads
        ADD CONSTRAINT fk_leads_status_definition_id
        FOREIGN KEY (status_definition_id) REFERENCES status_definitions(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE lead_status_history
        ADD CONSTRAINT lead_status_history_status_definition_id_fkey
        FOREIGN KEY (status_definition_id) REFERENCES status_definitions(id) ON DELETE RESTRICT
        """
    )


def downgrade() -> None:
    pass
