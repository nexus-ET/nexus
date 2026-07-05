-- status_definitions v3 (45 pipeline stages)
-- Run in Neon SQL Editor (staging/production) during a maintenance window.
--
-- WHAT THIS SCRIPT DOES
--   1. Remaps existing FK values (leads, status_history, lead_status_history) from v2 IDs → v3 IDs
--   2. Drops FK constraints that block status_definitions rebuild
--   3. Drops and recreates status_definitions with 45 rows + next_stage_id links
--   4. Rebuilds status_transitions (forward / express / backward / relaunch)
--   5. Restores FK constraints
--
-- ASSOCIATED TABLES (reference status_definitions.id)
--   leads.status_definition_id          ON DELETE SET NULL
--   status_history.status_id              ON DELETE RESTRICT  ← remapped before drop
--   lead_status_history.status_definition_id (if present) ON DELETE RESTRICT
--   status_transitions.from_status_id     ON DELETE CASCADE   ← truncated & reseeded
--   status_transitions.to_status_id       ON DELETE CASCADE
--   status_definitions.next_stage_id      self-reference SET NULL
--
-- v2 (39 rows) → v3 (45 rows) ID remap by stage meaning (run BEFORE drop):
--   Counselling block 10–15 → 12–17
--   Document block (new)    16–17 → 18–21
--   Admission+ shifted +2/+4 as listed in OLD_TO_NEW_STATUS_ID below
--   New rows 10–11 (Marketing Enabled/Disabled) have no v2 equivalent
--
-- BACKUP FIRST:
--   pg_dump or Neon branch snapshot before running.

BEGIN;

-- ---------------------------------------------------------------------------
-- A) Remap live FK references from status_definitions v2 IDs → v3 IDs
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'status_definition_id'
    ) THEN
        UPDATE leads
        SET status_definition_id = CASE status_definition_id
            WHEN 1 THEN 1   WHEN 2 THEN 2   WHEN 3 THEN 3   WHEN 4 THEN 4   WHEN 5 THEN 5
            WHEN 6 THEN 6   WHEN 7 THEN 7   WHEN 8 THEN 8   WHEN 9 THEN 9
            WHEN 10 THEN 12 WHEN 11 THEN 13 WHEN 12 THEN 14 WHEN 13 THEN 15
            WHEN 14 THEN 16 WHEN 15 THEN 17
            WHEN 16 THEN 18 WHEN 17 THEN 19
            WHEN 18 THEN 22 WHEN 19 THEN 24 WHEN 20 THEN 25 WHEN 21 THEN 26
            WHEN 22 THEN 27 WHEN 23 THEN 28 WHEN 24 THEN 29 WHEN 25 THEN 30
            WHEN 26 THEN 31 WHEN 27 THEN 33 WHEN 28 THEN 34 WHEN 29 THEN 35
            WHEN 30 THEN 36 WHEN 31 THEN 37 WHEN 32 THEN 38 WHEN 33 THEN 39
            WHEN 34 THEN 40 WHEN 35 THEN 41 WHEN 36 THEN 42
            WHEN 37 THEN 43 WHEN 38 THEN 44 WHEN 39 THEN 45
            ELSE status_definition_id
        END
        WHERE status_definition_id IS NOT NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'status_history'
    ) THEN
        UPDATE status_history
        SET status_id = CASE status_id
            WHEN 1 THEN 1   WHEN 2 THEN 2   WHEN 3 THEN 3   WHEN 4 THEN 4   WHEN 5 THEN 5
            WHEN 6 THEN 6   WHEN 7 THEN 7   WHEN 8 THEN 8   WHEN 9 THEN 9
            WHEN 10 THEN 12 WHEN 11 THEN 13 WHEN 12 THEN 14 WHEN 13 THEN 15
            WHEN 14 THEN 16 WHEN 15 THEN 17
            WHEN 16 THEN 18 WHEN 17 THEN 19
            WHEN 18 THEN 22 WHEN 19 THEN 24 WHEN 20 THEN 25 WHEN 21 THEN 26
            WHEN 22 THEN 27 WHEN 23 THEN 28 WHEN 24 THEN 29 WHEN 25 THEN 30
            WHEN 26 THEN 31 WHEN 27 THEN 33 WHEN 28 THEN 34 WHEN 29 THEN 35
            WHEN 30 THEN 36 WHEN 31 THEN 37 WHEN 32 THEN 38 WHEN 33 THEN 39
            WHEN 34 THEN 40 WHEN 35 THEN 41 WHEN 36 THEN 42
            WHEN 37 THEN 43 WHEN 38 THEN 44 WHEN 39 THEN 45
            ELSE status_id
        END;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'lead_status_history'
    ) THEN
        UPDATE lead_status_history
        SET status_definition_id = CASE status_definition_id
            WHEN 1 THEN 1   WHEN 2 THEN 2   WHEN 3 THEN 3   WHEN 4 THEN 4   WHEN 5 THEN 5
            WHEN 6 THEN 6   WHEN 7 THEN 7   WHEN 8 THEN 8   WHEN 9 THEN 9
            WHEN 10 THEN 12 WHEN 11 THEN 13 WHEN 12 THEN 14 WHEN 13 THEN 15
            WHEN 14 THEN 16 WHEN 15 THEN 17
            WHEN 16 THEN 18 WHEN 17 THEN 19
            WHEN 18 THEN 22 WHEN 19 THEN 24 WHEN 20 THEN 25 WHEN 21 THEN 26
            WHEN 22 THEN 27 WHEN 23 THEN 28 WHEN 24 THEN 29 WHEN 25 THEN 30
            WHEN 26 THEN 31 WHEN 27 THEN 33 WHEN 28 THEN 34 WHEN 29 THEN 35
            WHEN 30 THEN 36 WHEN 31 THEN 37 WHEN 32 THEN 38 WHEN 33 THEN 39
            WHEN 34 THEN 40 WHEN 35 THEN 41 WHEN 36 THEN 42
            WHEN 37 THEN 43 WHEN 38 THEN 44 WHEN 39 THEN 45
            ELSE status_definition_id
        END;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- B) Drop FK constraints that reference status_definitions
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS leads DROP CONSTRAINT IF EXISTS fk_leads_status_definition_id;
ALTER TABLE IF EXISTS leads DROP CONSTRAINT IF EXISTS leads_status_definition_id_fkey;

ALTER TABLE IF EXISTS status_history DROP CONSTRAINT IF EXISTS status_history_status_id_fkey;
ALTER TABLE IF EXISTS status_history DROP CONSTRAINT IF EXISTS fk_status_history_status_id;

ALTER TABLE IF EXISTS lead_status_history DROP CONSTRAINT IF EXISTS lead_status_history_status_definition_id_fkey;

-- status_transitions CASCADE from status_definitions; clear explicitly first
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'status_transitions'
    ) THEN
        TRUNCATE TABLE status_transitions RESTART IDENTITY;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- C) Drop and recreate status_definitions
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS status_definitions CASCADE;

CREATE TABLE status_definitions (
    id              SERIAL PRIMARY KEY,
    stage_name      VARCHAR(120) NOT NULL UNIQUE,
    category        VARCHAR(50)  NOT NULL,
    description     TEXT,
    next_stage_id   INT REFERENCES status_definitions(id) ON DELETE SET NULL
);

CREATE INDEX ix_status_definitions_id ON status_definitions (id);
CREATE UNIQUE INDEX ix_status_definitions_stage_name ON status_definitions (stage_name);
CREATE INDEX ix_status_definitions_category ON status_definitions (category);

-- ---------------------------------------------------------------------------
-- D) Insert all 45 stages (next_stage_id from pipeline spec)
-- ---------------------------------------------------------------------------
INSERT INTO status_definitions (id, stage_name, category, description, next_stage_id) VALUES
(1,  'Lead: New',                         'Lead',          'Initial inquiry received, pending first contact.',                    2),
(2,  'Lead: Outreach',                    'Lead',          'First outreach attempt initiated by advisor.',                          3),
(3,  'Lead: Engagement',                  'Lead',          'Active conversation established with the student.',                     4),
(4,  'Lead: Session Booked',              'Lead',          'Counselling session confirmed via WhatsApp.',                           5),
(5,  'Lead: Session Rescheduled',         'Lead',          'Student requested a change to the meeting time.',                       3),
(6,  'Lead: Session Cancelled',           'Lead',          'Student cancelled the initial meeting request.',                        3),
(7,  'Lead: Cancelled (No Answer)',        'Lead',          'Unresponsive after multiple outreach attempts.',                        10),
(8,  'Lead: Cancelled (Not Interested)',  'Lead',          'Student decided not to pursue services.',                               4),
(9,  'Lead: Deferred',                    'Lead',          'Interested but postponing plans to a later date.',                        10),
(10, 'Lead: Marketing Enabled',           'Lead',          'Lead is enrolled in the automated marketing sequence.',                 2),
(11, 'Lead: Marketing Disabled',          'Lead',          'Marketing outreach is disabled per lead''s request.',                   2),
(12, 'Counselling: Scheduled',            'Counselling',   'Appointment date and time finalized.',                                  13),
(13, 'Counselling: Finished',             'Counselling',   'Counselling session successfully completed.',                           14),
(14, 'Counselling: Prospect Qualified',   'Counselling',   'Student meets criteria, moving to application.',                        18),
(15, 'Counselling: Follow-up',            'Counselling',   'Additional session needed for clarity.',                                12),
(16, 'Counselling: Cancelled (Not Interested)', 'Counselling', 'Withdrew during the counselling phase.',                          11),
(17, 'Counselling: Deferred',             'Counselling',   'Counselling process paused by student request.',                        10),
(18, 'Document: In Preparation',          'Documentation', 'Gathering necessary documents for submission.',                           19),
(19, 'Document: Under Review',            'Documentation', 'Internal review of documentation for accuracy.',                          21),
(20, 'Document: Awaiting Submission',     'Documentation', 'Waiting for documents. Candidate is informed.',                           19),
(21, 'Document: Verification Complete',   'Documentation', 'Document verified and approved for the application.',                     22),
(22, 'Admission: Application Preparation','Admission',     'Admission documents preparation in progress.',                            23),
(23, 'Admission: Application Submitted',  'Admission',     'Application sent to the university.',                                     24),
(24, 'Admission: Application Assessment', 'Admission',     'Awaiting university decision or interview.',                              25),
(25, 'Admission: Application Accepted',   'Admission',     'University approval confirmed.',                                          26),
(26, 'Admission: Offer Letter Received',  'Admission',     'Official offer letter received and processed.',                           28),
(27, 'Admission: Application Rejected',   'Admission',     'University declined the application.',                                    45),
(28, 'Visa: Application Document Prep',   'Visa',          'Preparing financial and immigration evidence.',                           29),
(29, 'Visa: Application Filing',          'Visa',          'Application submitted to visa authorities.',                              30),
(30, 'Visa: Application Processing',    'Visa',          'Embassy is currently reviewing the file.',                                31),
(31, 'Visa: Mock Interview',              'Visa',          'Candidate is practicing simulated interview sessions.',                   32),
(32, 'Visa: Officer Interview',           'Visa',          'Candidate is scheduled to attend embassy interview.',                     33),
(33, 'Visa: Application Approved',        'Visa',          'Visa application has been granted.',                                    34),
(34, 'Visa: Issued/Collected',            'Visa',          'Visa stamped and passport retrieved.',                                  36),
(35, 'Visa: Application Rejected',        'Visa',          'Visa application was declined.',                                          45),
(36, 'Pre-Departure: Orientation',        'Pre-Departure', 'Attending pre-departure briefing.',                                     37),
(37, 'Pre-Departure: Travel/Insurance/ForEx', 'Pre-Departure', 'Finalizing travel, insurance, and currency.',                       38),
(38, 'Pre-Departure: Accommodation',      'Pre-Departure', 'Housing secured for arrival.',                                          39),
(39, 'Pre-Departure: Documentation Assessment', 'Pre-Departure', 'Pre-Departure Required Documents Assessment.',                    40),
(40, 'Pre-Departure: Travel Confirmed',   'Pre-Departure', 'All travel logistics verified.',                                        41),
(41, 'Arrival: Landed',                   'Arrival',       'Student arrived in target country.',                                    42),
(42, 'Arrival: Campus Reporting',         'Arrival',       'Reported to the university office.',                                    43),
(43, 'Prospect: Enrolled & Closed',       'Prospect',      'Successfully enrolled and settled.',                                    10),
(44, 'Prospect: Cancelled & Closed',      'Prospect',      'Process permanently terminated.',                                       11),
(45, 'Prospect: Relaunch',                'Prospect',      'Restarting process after change/rejection.',                            1);

SELECT setval('status_definitions_id_seq', (SELECT MAX(id) FROM status_definitions));

-- ---------------------------------------------------------------------------
-- E) Rebuild status_transitions (requires status_transition_type enum + table)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'status_transitions'
    ) THEN
        -- Forward paths from next_stage_id
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
        SELECT id, next_stage_id, 'forward'
        FROM status_definitions
        WHERE next_stage_id IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING;

        -- Express jumps (admin / manager only in app)
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type) VALUES
            (1,  12, 'express'),  -- Lead: New → Counselling: Scheduled
            (3,  18, 'express'),  -- Lead: Engagement → Document: In Preparation
            (13, 28, 'express')   -- Counselling: Finished → Visa: Application Document Prep
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING;

        -- Relaunch
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type) VALUES
            (44, 45, 'relaunch')  -- Prospect: Cancelled & Closed → Prospect: Relaunch
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING;

        -- Backward = reverse of forward
        INSERT INTO status_transitions (from_status_id, to_status_id, transition_type)
        SELECT to_status_id, from_status_id, 'backward'
        FROM status_transitions
        WHERE transition_type = 'forward'
        ON CONFLICT ON CONSTRAINT uq_status_transitions_from_to_type DO NOTHING;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- F) Restore FK constraints
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'status_definition_id'
    ) THEN
        ALTER TABLE leads
            ADD CONSTRAINT fk_leads_status_definition_id
            FOREIGN KEY (status_definition_id) REFERENCES status_definitions(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'status_history'
    ) THEN
        ALTER TABLE status_history
            ADD CONSTRAINT status_history_status_id_fkey
            FOREIGN KEY (status_id) REFERENCES status_definitions(id) ON DELETE RESTRICT;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'lead_status_history'
    ) THEN
        ALTER TABLE lead_status_history
            ADD CONSTRAINT lead_status_history_status_definition_id_fkey
            FOREIGN KEY (status_definition_id) REFERENCES status_definitions(id) ON DELETE RESTRICT;
    END IF;
END $$;

COMMIT;

-- ---------------------------------------------------------------------------
-- G) Verify
-- ---------------------------------------------------------------------------
SELECT COUNT(*) AS status_definition_count FROM status_definitions;
SELECT id, stage_name, category, next_stage_id FROM status_definitions ORDER BY id;
SELECT transition_type, COUNT(*) FROM status_transitions GROUP BY 1 ORDER BY 1;
