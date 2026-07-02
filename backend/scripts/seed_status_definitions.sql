-- status_definitions v2 (39 pipeline stages)
-- Paste this SQL into Neon SQL Editor (copy file CONTENTS, not the path).

-- A) Drop table
DROP TABLE IF EXISTS status_definitions CASCADE;

-- B) Create table & insert data
CREATE TABLE status_definitions (
    id SERIAL PRIMARY KEY,
    stage_name VARCHAR(120) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    description TEXT,
    next_stage_id INT REFERENCES status_definitions(id) ON DELETE SET NULL
);

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
(39, 'Prospect: Relaunch', 'Prospect', 'Restarting process after change/rejection.');

SELECT setval('status_definitions_id_seq', (SELECT MAX(id) FROM status_definitions));

-- C) Update next_stage_id flow
UPDATE status_definitions SET next_stage_id = id + 1 WHERE id IN (1, 2, 3, 10, 11, 16, 17, 18, 19, 20, 23, 24, 25, 26, 27, 30, 31, 32, 33, 35);

-- Branch transitions
UPDATE status_definitions SET next_stage_id = 10 WHERE id IN (4, 5, 13);
UPDATE status_definitions SET next_stage_id = 4 WHERE id = 6;
UPDATE status_definitions SET next_stage_id = 16 WHERE id = 12;
UPDATE status_definitions SET next_stage_id = 23 WHERE id = 21;
UPDATE status_definitions SET next_stage_id = 35 WHERE id = 34;

-- Terminal stages (no automatic next step)
UPDATE status_definitions SET next_stage_id = NULL
WHERE id IN (7, 8, 9, 14, 15, 22, 29, 37, 38, 39);
