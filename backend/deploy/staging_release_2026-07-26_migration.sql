-- =============================================================================
-- NEXUS Staging consolidated migration
-- Release package date: 2026-07-26
-- Target: bring Staging (Neon / nexus-dev) from alembic head c4d7e0f53g6h
--         to f7y0d3esolution
--
-- Prefer:  alembic upgrade head   (from backend/ with staging DATABASE_URL)
-- Use this SQL only if you must apply by hand / DBA review.
-- Safe to re-run: uses IF NOT EXISTS / conditional ADD COLUMN patterns.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 1) d5e8f1a64h7i — Phase 1 university matching
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS matching_weight_profiles (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    weight_academic NUMERIC(5, 4) NOT NULL,
    weight_profile NUMERIC(5, 4) NOT NULL,
    weight_aspirations NUMERIC(5, 4) NOT NULL,
    weight_safety NUMERIC(5, 4) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_matching_weight_profiles_id ON matching_weight_profiles (id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_matching_weight_profiles_code ON matching_weight_profiles (code);

CREATE TABLE IF NOT EXISTS matching_shortlist_runs (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    booking_id INTEGER REFERENCES counselling_bookings(id) ON DELETE SET NULL,
    students_master_id INTEGER REFERENCES students_master(id) ON DELETE SET NULL,
    weight_profile_id INTEGER REFERENCES matching_weight_profiles(id) ON DELETE SET NULL,
    algorithm_version VARCHAR(40) NOT NULL DEFAULT 'phase1-v1',
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    classification_mode VARCHAR(40) NOT NULL DEFAULT 'heuristic_fit',
    item_count INTEGER NOT NULL DEFAULT 0,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    input_snapshot JSONB,
    notes TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_id ON matching_shortlist_runs (id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_lead_id ON matching_shortlist_runs (lead_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_booking_id ON matching_shortlist_runs (booking_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_students_master_id ON matching_shortlist_runs (students_master_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_weight_profile_id ON matching_shortlist_runs (weight_profile_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_algorithm_version ON matching_shortlist_runs (algorithm_version);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_status ON matching_shortlist_runs (status);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_runs_created_at ON matching_shortlist_runs (created_at);

CREATE TABLE IF NOT EXISTS matching_shortlist_items (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES matching_shortlist_runs(id) ON DELETE CASCADE,
    institution_id INTEGER NOT NULL REFERENCES institutions(id) ON DELETE CASCADE,
    offering_id INTEGER REFERENCES institution_course_offerings(id) ON DELETE SET NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    consolidated_score NUMERIC(6, 2) NOT NULL,
    s_academic NUMERIC(6, 2) NOT NULL,
    s_profile NUMERIC(6, 2) NOT NULL,
    s_aspirations NUMERIC(6, 2) NOT NULL,
    s_safety NUMERIC(6, 2) NOT NULL,
    fit_band VARCHAR(20) NOT NULL,
    explanation JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_shortlist_run_inst_offering UNIQUE (run_id, institution_id, offering_id)
);

CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_id ON matching_shortlist_items (id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_run_id ON matching_shortlist_items (run_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_institution_id ON matching_shortlist_items (institution_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_offering_id ON matching_shortlist_items (offering_id);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_rank ON matching_shortlist_items (rank);
CREATE INDEX IF NOT EXISTS ix_matching_shortlist_items_fit_band ON matching_shortlist_items (fit_band);

INSERT INTO matching_weight_profiles (
    code, name, description,
    weight_academic, weight_profile, weight_aspirations, weight_safety,
    is_default, is_active
)
VALUES
    (
        'default',
        'Default (balanced)',
        'Phase 1 balanced weights for general master''s shortlists.',
        0.3500, 0.2500, 0.3000, 0.1000,
        true, true
    ),
    (
        'research_masters',
        'Research master''s',
        'Higher weight on profile/research strength for research-oriented programs.',
        0.3500, 0.4000, 0.1500, 0.1000,
        false, true
    )
ON CONFLICT (code) DO NOTHING;

-- -----------------------------------------------------------------------------
-- 2) e6x9c2eption01 — exception_logs table (Exception Report)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exception_logs (
    id SERIAL PRIMARY KEY,
    severity VARCHAR(20) NOT NULL,
    source VARCHAR(50) NOT NULL,
    category VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    triggered_by_user VARCHAR(255) NOT NULL,
    triggered_by_user_id INTEGER,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL,
    page_path VARCHAR(255),
    exception_type VARCHAR(120),
    related_resource VARCHAR(100),
    related_id VARCHAR(100),
    attempt_timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE,
    resolved_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_exception_logs_id ON exception_logs (id);
CREATE INDEX IF NOT EXISTS ix_exception_logs_severity ON exception_logs (severity);
CREATE INDEX IF NOT EXISTS ix_exception_logs_source ON exception_logs (source);
CREATE INDEX IF NOT EXISTS ix_exception_logs_category ON exception_logs (category);
CREATE INDEX IF NOT EXISTS ix_exception_logs_status ON exception_logs (status);
CREATE INDEX IF NOT EXISTS ix_exception_logs_triggered_by_user ON exception_logs (triggered_by_user);
CREATE INDEX IF NOT EXISTS ix_exception_logs_triggered_by_user_id ON exception_logs (triggered_by_user_id);
CREATE INDEX IF NOT EXISTS ix_exception_logs_attempt_timestamp ON exception_logs (attempt_timestamp);
CREATE INDEX IF NOT EXISTS ix_exception_logs_created_at ON exception_logs (created_at);

-- -----------------------------------------------------------------------------
-- 3) f7y0d3esolution — resolution_comment on exception_logs
-- -----------------------------------------------------------------------------
ALTER TABLE exception_logs
    ADD COLUMN IF NOT EXISTS resolution_comment TEXT;

-- -----------------------------------------------------------------------------
-- Stamp Alembic version (only if applying this SQL by hand instead of alembic)
-- Skip this block when using: alembic upgrade head
-- -----------------------------------------------------------------------------
-- INSERT INTO alembic_version (version_num) VALUES ('f7y0d3esolution')
-- ON CONFLICT DO NOTHING;
-- Or: UPDATE alembic_version SET version_num = 'f7y0d3esolution';

COMMIT;

-- Verification queries (run after apply):
-- SELECT version_num FROM alembic_version;
-- SELECT code, is_default FROM matching_weight_profiles ORDER BY code;
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'exception_logs' ORDER BY ordinal_position;
