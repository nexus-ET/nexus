"""Bootstrap status_definitions v3 when the table exists but Alembic seed did not run."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

V3_INSERT_SQL = """
INSERT INTO status_definitions (id, stage_name, category, description, next_stage_id) VALUES
(1,  'Lead: New', 'Lead', 'Initial inquiry received, pending first contact.', 2),
(2,  'Lead: Outreach', 'Lead', 'First outreach attempt initiated by advisor.', 3),
(3,  'Lead: Engagement', 'Lead', 'Active conversation established with the student.', 4),
(4,  'Lead: Session Booked', 'Lead', 'Counselling session confirmed via WhatsApp.', 5),
(5,  'Lead: Session Rescheduled', 'Lead', 'Student requested a change to the meeting time.', 3),
(6,  'Lead: Session Cancelled', 'Lead', 'Student cancelled the initial meeting request.', 3),
(7,  'Lead: Cancelled (No Answer)', 'Lead', 'Unresponsive after multiple outreach attempts.', 10),
(8,  'Lead: Cancelled (Not Interested)', 'Lead', 'Student decided not to pursue services.', 4),
(9,  'Lead: Deferred', 'Lead', 'Interested but postponing plans to a later date.', 10),
(10, 'Lead: Marketing Enabled', 'Lead', 'Lead is enrolled in the automated marketing sequence.', 2),
(11, 'Lead: Marketing Disabled', 'Lead', 'Marketing outreach is disabled per lead''s request.', 2),
(12, 'Counselling: Scheduled', 'Counselling', 'Appointment date and time finalized.', 13),
(13, 'Counselling: Finished', 'Counselling', 'Counselling session successfully completed.', 14),
(14, 'Counselling: Prospect Qualified', 'Counselling', 'Student meets criteria, moving to application.', 18),
(15, 'Counselling: Follow-up', 'Counselling', 'Additional session needed for clarity.', 12),
(16, 'Counselling: Cancelled (Not Interested)', 'Counselling', 'Withdrew during the counselling phase.', 11),
(17, 'Counselling: Deferred', 'Counselling', 'Counselling process paused by student request.', 10),
(18, 'Document: In Preparation', 'Documentation', 'Gathering necessary documents for submission.', 19),
(19, 'Document: Under Review', 'Documentation', 'Internal review of documentation for accuracy.', 21),
(20, 'Document: Awaiting Submission', 'Documentation', 'Waiting for documents. Candidate is informed.', 19),
(21, 'Document: Verification Complete', 'Documentation', 'Document verified and approved for the application.', 22),
(22, 'Admission: Application Preparation', 'Admission', 'Admission documents preparation in progress.', 23),
(23, 'Admission: Application Submitted', 'Admission', 'Application sent to the university.', 24),
(24, 'Admission: Application Assessment', 'Admission', 'Awaiting university decision or interview.', 25),
(25, 'Admission: Application Accepted', 'Admission', 'University approval confirmed.', 26),
(26, 'Admission: Offer Letter Received', 'Admission', 'Official offer letter received and processed.', 28),
(27, 'Admission: Application Rejected', 'Admission', 'University declined the application.', 45),
(28, 'Visa: Application Document Prep', 'Visa', 'Preparing financial and immigration evidence.', 29),
(29, 'Visa: Application Filing', 'Visa', 'Application submitted to visa authorities.', 30),
(30, 'Visa: Application Processing', 'Visa', 'Embassy is currently reviewing the file.', 31),
(31, 'Visa: Mock Interview', 'Visa', 'Candidate is practicing simulated interview sessions.', 32),
(32, 'Visa: Officer Interview', 'Visa', 'Candidate is scheduled to attend embassy interview.', 33),
(33, 'Visa: Application Approved', 'Visa', 'Visa application has been granted.', 34),
(34, 'Visa: Issued/Collected', 'Visa', 'Visa stamped and passport retrieved.', 36),
(35, 'Visa: Application Rejected', 'Visa', 'Visa application was declined.', 45),
(36, 'Pre-Departure: Orientation', 'Pre-Departure', 'Attending pre-departure briefing.', 37),
(37, 'Pre-Departure: Travel/Insurance/ForEx', 'Pre-Departure', 'Finalizing travel, insurance, and currency.', 38),
(38, 'Pre-Departure: Accommodation', 'Pre-Departure', 'Housing secured for arrival.', 39),
(39, 'Pre-Departure: Documentation Assessment', 'Pre-Departure', 'Pre-Departure Required Documents Assessment.', 40),
(40, 'Pre-Departure: Travel Confirmed', 'Pre-Departure', 'All travel logistics verified.', 41),
(41, 'Arrival: Landed', 'Arrival', 'Student arrived in target country.', 42),
(42, 'Arrival: Campus Reporting', 'Arrival', 'Reported to the university office.', 43),
(43, 'Prospect: Enrolled & Closed', 'Prospect', 'Successfully enrolled and settled.', 10),
(44, 'Prospect: Cancelled & Closed', 'Prospect', 'Process permanently terminated.', 11),
(45, 'Prospect: Relaunch', 'Prospect', 'Restarting process after change/rejection.', 1)
"""


def seed_status_definitions_if_empty(db: Session) -> bool:
    """
    Insert the 45 pipeline stages when status_definitions has no rows.

    Staging databases that used create_all() without Alembic end up with an empty
    table — View Journey and pipeline status dropdowns then show nothing.
    """
    from app.models.status_definition import StatusDefinition
    from app.services.status_definition_service import (
        STAGE_LEAD_ENGAGEMENT,
        STAGE_LEAD_NEW,
        STAGE_LEAD_OUTREACH,
        STAGE_LEAD_SESSION_BOOKED,
    )

    if db.query(StatusDefinition.id).limit(1).first() is not None:
        return False

    logger.warning("status_definitions is empty — seeding v3 pipeline stages.")

    db.execute(text(V3_INSERT_SQL))
    db.execute(text("SELECT setval('status_definitions_id_seq', (SELECT MAX(id) FROM status_definitions))"))
    db.commit()
    logger.info("Seeded 45 status_definitions rows.")
    return True


def ensure_status_definition_funnel_links(db: Session) -> bool:
    """
    Repair next_stage_id links for the lead funnel when missing (common on partial migrations).
    """
    from app.services.status_definition_service import (
        STAGE_LEAD_ENGAGEMENT,
        STAGE_LEAD_NEW,
        STAGE_LEAD_OUTREACH,
        STAGE_LEAD_SESSION_BOOKED,
        get_status_definition_by_name,
    )

    changed = False
    funnel_links = (
        (STAGE_LEAD_NEW, STAGE_LEAD_OUTREACH),
        (STAGE_LEAD_OUTREACH, STAGE_LEAD_ENGAGEMENT),
        (STAGE_LEAD_ENGAGEMENT, STAGE_LEAD_SESSION_BOOKED),
    )
    for current_name, next_name in funnel_links:
        current = get_status_definition_by_name(db, current_name)
        nxt = get_status_definition_by_name(db, next_name)
        if current is None or nxt is None:
            continue
        if current.next_stage_id != nxt.id:
            current.next_stage_id = nxt.id
            changed = True
    if changed:
        db.commit()
        logger.info("Repaired status_definitions funnel next_stage_id links.")
    return changed
