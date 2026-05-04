-- ============================================================================
-- MNEMEX initial schema
-- Migration: 20260504_001_initial_schema.sql
-- ============================================================================
--
-- This is the foundation migration for MNEMEX. It establishes:
--   - Tables: competitors, results, ingestion_runs, reconciliation_queue,
--             strathex_inbox, federations
--   - Indexes for the hot paths (STRATHMARK sync, reconciliation matching,
--             per-competitor lookups, ingestion audit)
--   - canonical_chopping_results view (read-only surface for STRATHMARK)
--   - RLS roles: strathmark_read, strathex_write
--   - Federation seed data
--
-- Apply via the Supabase CLI:
--     supabase db push --project-ref <mnemex-prod-ref>
-- Or via the dashboard SQL editor (paste this whole file).
--
-- This migration is idempotent up to the table-creation step. Re-running it
-- after any of the IF NOT EXISTS clauses are satisfied will be a no-op for
-- those sections. Re-applying after rows exist requires care; see
-- mnemex/migrations/README.md.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Tables
-- ----------------------------------------------------------------------------

-- competitors: canonical athlete identities, with per-federation IDs
-- and disambiguation tiebreakers (year-only birth, city/state hometown).
-- Mirrors mnemex.identity.CanonicalAthlete from PR 1.
CREATE TABLE IF NOT EXISTS competitors (
    competitor_id     TEXT        PRIMARY KEY,                          -- ULID
    canonical_name    TEXT        NOT NULL,
    federation_ids    JSONB       NOT NULL DEFAULT '{}'::jsonb,         -- {"stihl": "12345", "awfc": "OSU-2022-018"}
    aliases           TEXT[]      NOT NULL DEFAULT '{}',
    birth_year        INT,                                              -- year only; never full DOB (privacy)
    hometown          TEXT,                                             -- "Missoula, MT"; never street address
    eligibility       JSONB,                                            -- per-year status [{year, status}]
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_modified_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ingestion_runs: one row per scraper run / federation upload / STRATHEX
-- finalization. Used as FK from results.ingestion_run_id for audit and
-- replay. Mirrors mnemex.ingestion_runs.IngestionRun from PR 1.
CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id            TEXT        PRIMARY KEY,                          -- ULID
    source_type       TEXT        NOT NULL,                             -- scraper | federation_upload | strathex_finalization
    started_at        TIMESTAMPTZ NOT NULL,
    completed_at      TIMESTAMPTZ,
    status            TEXT        NOT NULL DEFAULT 'running',           -- running | succeeded | failed | partial
    rows_ingested     INT         NOT NULL DEFAULT 0,
    operator          TEXT,
    notes             TEXT
);

-- results: canonical results table. One row per competitor per discipline
-- per event. Pair events emit two rows linked via partner_competitor_id.
-- Mirrors mnemex.schema.CanonicalRow from PR 1.
CREATE TABLE IF NOT EXISTS results (
    result_id              TEXT        PRIMARY KEY,                          -- ULID
    competitor_id          TEXT        NOT NULL REFERENCES competitors(competitor_id),
    discipline             TEXT        NOT NULL,                             -- matches Discipline enum
    event_date             DATE        NOT NULL,
    event_name             TEXT        NOT NULL,
    event_circuit          TEXT        NOT NULL,                             -- matches EventCircuit enum
    division               TEXT        NOT NULL,                             -- matches Division enum
    governing_body         TEXT        NOT NULL,
    log_species            TEXT,
    log_diameter_mm        INT,
    log_length_mm          INT,
    log_specification      TEXT,
    final_score            NUMERIC,                                          -- seconds for time, points for raw_score
    score_type             TEXT        NOT NULL,                             -- matches ScoreType enum
    final_score_policy     TEXT        NOT NULL,                             -- matches FinalScorePolicy enum
    handicap_mark          NUMERIC,
    partner_competitor_id  TEXT        REFERENCES competitors(competitor_id),-- non-null for pair events
    dq_flag                BOOLEAN     NOT NULL DEFAULT FALSE,
    dq_reason              TEXT,                                             -- matches DQReason enum
    no_time_flag           BOOLEAN     NOT NULL DEFAULT FALSE,
    scratch_flag           BOOLEAN     NOT NULL DEFAULT FALSE,
    runs                   JSONB,                                            -- per-run scores for multi-run events
    -- provenance
    source_type            TEXT        NOT NULL,                             -- matches SourceType enum
    source_id              TEXT        NOT NULL,
    source_native_id       TEXT,                                             -- distinct provenance level
    ingestion_run_id       TEXT        NOT NULL REFERENCES ingestion_runs(run_id),
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- reconciliation
    provisional            BOOLEAN     NOT NULL DEFAULT TRUE,
    canonical_id           TEXT        REFERENCES results(result_id),         -- self-FK; non-null = "superseded by"
    reconciled_at          TIMESTAMPTZ,
    last_modified_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- reconciliation_queue: populated by the reconciliation worker (PR 5).
-- Schema lands now so the RLS policies and indexes are in place.
CREATE TABLE IF NOT EXISTS reconciliation_queue (
    queue_id                       TEXT        PRIMARY KEY,                  -- ULID
    provisional_result_id          TEXT        NOT NULL REFERENCES results(result_id),
    candidate_canonical_result_id  TEXT        REFERENCES results(result_id),
    match_score                    NUMERIC,                                  -- 0.0 - 1.0
    disagreements                  JSONB,                                    -- field-level disagreement details
    status                         TEXT        NOT NULL DEFAULT 'pending',   -- pending | auto_reconciled | needs_review | rejected
    created_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at                    TIMESTAMPTZ,
    resolved_by                    TEXT
);

-- strathex_inbox: populated by the STRATHEX webhook (PR 4). Schema lands
-- now so the strathex_write RLS role can be configured. Idempotency is
-- enforced via UNIQUE(strathex_event_id) so STRATHEX retries don't
-- produce duplicate inbox rows.
CREATE TABLE IF NOT EXISTS strathex_inbox (
    inbox_id           TEXT        PRIMARY KEY,                              -- ULID
    strathex_event_id  TEXT        NOT NULL UNIQUE,                          -- idempotency key
    payload            JSONB       NOT NULL,
    received_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at       TIMESTAMPTZ,
    result_ids         TEXT[],                                               -- canonical result IDs assigned
    status             TEXT        NOT NULL DEFAULT 'received',              -- received | processed | failed
    error_message      TEXT
);

-- federations: reference table. Lookup for federation slugs used in
-- competitors.federation_ids and results.governing_body.
CREATE TABLE IF NOT EXISTS federations (
    federation_slug      TEXT PRIMARY KEY,                                   -- lowercase short string
    display_name         TEXT NOT NULL,
    governing_body_full  TEXT NOT NULL,
    website              TEXT,
    notes                TEXT
);


-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------

-- STRATHMARK sync filter: discipline + last_modified_at watermark
CREATE INDEX IF NOT EXISTS idx_results_discipline_last_modified
    ON results(discipline, last_modified_at);

-- Reconciliation matching: events identified by (date, name)
CREATE INDEX IF NOT EXISTS idx_results_event_date_name
    ON results(event_date, event_name);

-- Per-competitor history queries
CREATE INDEX IF NOT EXISTS idx_results_competitor_id
    ON results(competitor_id);

-- Ingestion audit: which run produced which row, by source type
CREATE INDEX IF NOT EXISTS idx_results_source_type_run_id
    ON results(source_type, ingestion_run_id);

-- Supersession lookups: only the rows that have been superseded
CREATE INDEX IF NOT EXISTS idx_results_canonical_id
    ON results(canonical_id) WHERE canonical_id IS NOT NULL;

-- Reconciliation queue filtering by status (pending vs resolved)
CREATE INDEX IF NOT EXISTS idx_reconciliation_queue_status
    ON reconciliation_queue(status);

-- STRATHEX inbox: find unprocessed payloads
CREATE INDEX IF NOT EXISTS idx_strathex_inbox_status
    ON strathex_inbox(status) WHERE status = 'received';

-- Competitors: federation_ids lookups via JSONB GIN
-- Used when an ingest path encounters a federation-specific ID and needs
-- to find the canonical competitor it maps to.
CREATE INDEX IF NOT EXISTS idx_competitors_federation_ids_gin
    ON competitors USING GIN (federation_ids);

-- Competitors: alias lookups via array GIN
CREATE INDEX IF NOT EXISTS idx_competitors_aliases_gin
    ON competitors USING GIN (aliases);


-- ----------------------------------------------------------------------------
-- Read-only canonical view for STRATHMARK
-- ----------------------------------------------------------------------------
--
-- canonical_chopping_results filters results to:
--   - chopping disciplines only (the disciplines STRATHMARK models)
--   - canonical rows only (provisional rows that haven't been superseded
--     are EXCLUDED; canonical rows that have been superseded are also
--     EXCLUDED via canonical_id IS NULL)
--   - exposes only the columns STRATHMARK needs; provenance / operational
--     columns are hidden at this surface
--
-- STRATHMARK's read role (strathmark_read) has SELECT on this view only.
-- It cannot reach the base tables directly, so the provenance machinery
-- stays operationally separate from the prediction-engine concern.
CREATE OR REPLACE VIEW canonical_chopping_results AS
SELECT
    result_id,
    competitor_id,
    discipline,
    event_date,
    event_name,
    event_circuit,
    division,
    governing_body,
    log_species,
    log_diameter_mm,
    log_length_mm,
    log_specification,
    final_score,
    score_type,
    final_score_policy,
    handicap_mark,
    partner_competitor_id,
    dq_flag,
    dq_reason,
    no_time_flag,
    scratch_flag,
    runs,
    last_modified_at
FROM results
WHERE
    discipline IN (
        -- The chopping disciplines STRATHMARK models. Maps to TIER1 in
        -- mnemex.schema; explicitly enumerated here to make the view
        -- self-documenting and immune to a Tier-1 set rename.
        'STANDING_BLOCK',
        'UNDERHAND',
        'STOCK_SAW',
        'SINGLE_BUCK',
        'HOT_SAW',
        'SPRINGBOARD_1BD',
        'SPRINGBOARD_2BD',
        'DOUBLE_BUCK',
        'JACK_AND_JILL',
        'OBSTACLE_POLE',
        'POWER_SAW',
        'HORIZONTAL_SPEED',
        'VERTICAL_SPEED'
    )
    AND (provisional = FALSE OR canonical_id IS NOT NULL)
    AND canonical_id IS NULL;


-- ----------------------------------------------------------------------------
-- Row-Level Security
-- ----------------------------------------------------------------------------
--
-- Three roles operate on this database:
--
--   service_role  : Supabase default. Full access. Used by MNEMEX's own
--                    code (scrapers, reconciliation worker, JSONL exporter).
--                    Inherent to Supabase; not created here.
--
--   strathmark_read : NEW. SELECT-only on canonical_chopping_results.
--                     No access to any base table. Used by STRATHMARK
--                     when it pulls chopping data for the prediction
--                     cascade (PR 3 implements the sync triggers).
--
--   strathex_write  : NEW. INSERT-only on strathex_inbox. No access to
--                     any other table. Used by the STRATHEX finalization
--                     webhook (PR 4 implements the webhook handler).
--
-- See docs/supabase-rls-policies.md for the full role contract.
-- ----------------------------------------------------------------------------

-- Enable RLS on all base tables
ALTER TABLE competitors           ENABLE ROW LEVEL SECURITY;
ALTER TABLE results               ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_runs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE reconciliation_queue  ENABLE ROW LEVEL SECURITY;
ALTER TABLE strathex_inbox        ENABLE ROW LEVEL SECURITY;
ALTER TABLE federations           ENABLE ROW LEVEL SECURITY;

-- service_role bypasses RLS by default in Supabase. No policy needed.

-- Create the strathmark_read role if it doesn't exist.
-- We set NOLOGIN since this is a database role used by Supabase's
-- API gateway, not a direct-connect Postgres login.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'strathmark_read') THEN
        CREATE ROLE strathmark_read NOLOGIN;
    END IF;
END
$$;

-- strathmark_read: SELECT only on the view. NO access to base tables.
GRANT SELECT ON canonical_chopping_results TO strathmark_read;

-- Defensive: revoke base-table access in case Supabase grants a default.
REVOKE ALL ON results              FROM strathmark_read;
REVOKE ALL ON competitors          FROM strathmark_read;
REVOKE ALL ON ingestion_runs       FROM strathmark_read;
REVOKE ALL ON reconciliation_queue FROM strathmark_read;
REVOKE ALL ON strathex_inbox       FROM strathmark_read;
REVOKE ALL ON federations          FROM strathmark_read;

-- Create the strathex_write role.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'strathex_write') THEN
        CREATE ROLE strathex_write NOLOGIN;
    END IF;
END
$$;

-- strathex_write: INSERT only on strathex_inbox. NO read access anywhere.
-- The webhook handler (PR 4) authenticates STRATHEX, validates the
-- payload, and INSERTs a single inbox row. MNEMEX's reconciliation
-- worker (PR 5) reads the inbox using service_role.
CREATE POLICY strathex_inbox_insert_only
    ON strathex_inbox
    FOR INSERT
    TO strathex_write
    WITH CHECK (true);

GRANT INSERT ON strathex_inbox TO strathex_write;

-- Defensive: deny everything else for strathex_write.
REVOKE SELECT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON strathex_inbox        FROM strathex_write;
REVOKE ALL ON results               FROM strathex_write;
REVOKE ALL ON competitors           FROM strathex_write;
REVOKE ALL ON ingestion_runs        FROM strathex_write;
REVOKE ALL ON reconciliation_queue  FROM strathex_write;
REVOKE ALL ON federations           FROM strathex_write;
REVOKE ALL ON canonical_chopping_results FROM strathex_write;


-- ----------------------------------------------------------------------------
-- Federation seed data
-- ----------------------------------------------------------------------------
INSERT INTO federations (federation_slug, display_name, governing_body_full, website, notes) VALUES
    ('stihl',   'STIHL Pro Series',                 'STIHL TIMBERSPORTS Pro Series',                       'https://www.stihl-timbersports.com/',       'Professional series; primary scraping target.'),
    ('aaa',     'Australian Axemen''s Association', 'Australian Axemen''s Association',                    'https://www.axemen.org.au/',                'Pacific region governing body.'),
    ('awfc',    'AWFC Conclaves',                   'Association of Western Forestry Clubs',               NULL,                                        'Intercollegiate conclaves across North America.'),
    ('ala',     'American Lumberjack Association',  'American Lumberjack Association',                     'https://www.americanlumberjacks.com/',      'US club / association circuit.'),
    ('lwc',     'Lumberjack World Championship',    'Lumberjack World Championships, Inc.',                'https://www.lumberjackworldchampionships.com/', 'Annual championship in Hayward, WI.'),
    ('osu',     'OSU Forestry Club',                'Oregon State University Forestry Club',               'https://forestryclub.oregonstate.edu/',     'AWFC conclave host.'),
    ('csu',     'CSU Forestry Club',                'Colorado State University Forestry Club',             NULL,                                        'AWFC conclave host.'),
    ('uidaho',  'U Idaho Forestry Club',            'University of Idaho Associated Forestry Sports Club', NULL,                                        'AWFC conclave host.'),
    ('umont',   'U Montana Forestry Club',          'University of Montana Forestry Club',                 NULL,                                        'AWFC conclave host.')
ON CONFLICT (federation_slug) DO NOTHING;
