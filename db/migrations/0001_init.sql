-- MemoryBridge — initial schema
-- Run once against the Neon PostgreSQL project:
--   psql "$DATABASE_URL" -f db/migrations/0001_init.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- caregivers
-- Primary account holders. Password is bcrypt-hashed; the raw value never
-- leaves the web service. No PII beyond name + email is stored here.
-- ---------------------------------------------------------------------------
CREATE TABLE caregivers (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- assisted_users
-- One assisted user per caregiver in v1. The timezone field is used to
-- determine which routines are "due today" in GET /internal/today.
-- ---------------------------------------------------------------------------
CREATE TABLE assisted_users (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    caregiver_id UUID        NOT NULL REFERENCES caregivers(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    timezone     TEXT        NOT NULL DEFAULT 'UTC',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- routines
-- A row is inserted the moment a caregiver request is received — before
-- Stage 0 runs — so every request is visible in history with a reason.
-- status transitions: pending_caregiver_approval → active | rejected → archived
-- The CHECK constraint is the database-level enforcement of the state machine
-- (architecture.md §6.2); the application-layer enforcement is in the FastAPI
-- routers and the MCP write tools.
-- ---------------------------------------------------------------------------
CREATE TABLE routines (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assisted_user_id  UUID        NOT NULL REFERENCES assisted_users(id) ON DELETE CASCADE,
    caregiver_id      UUID        NOT NULL REFERENCES caregivers(id)     ON DELETE CASCADE,
    raw_request       TEXT        NOT NULL,
    title             TEXT,
    scheduled_time    TIME,
    recurrence        TEXT,
    status            TEXT        NOT NULL DEFAULT 'pending_caregiver_approval'
                          CHECK (status IN (
                              'pending_caregiver_approval',
                              'active',
                              'rejected',
                              'archived'
                          )),
    safety_verdict    TEXT,
    safety_reason     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at       TIMESTAMPTZ,
    activated_at      TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- routine_steps
-- One row per step. step_number is 1-indexed and unique per routine.
-- simplified_text is what Maria sees; original_text is the Planning Agent's
-- output before the Communication Agent rewrote it (audit trail).
-- ---------------------------------------------------------------------------
CREATE TABLE routine_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    routine_id      UUID NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    step_number     INT  NOT NULL,
    original_text   TEXT NOT NULL,
    simplified_text TEXT,
    UNIQUE (routine_id, step_number)
);

-- ---------------------------------------------------------------------------
-- routine_completions
-- One row per (routine, calendar date) when Maria taps Done.
-- The UNIQUE constraint prevents double-completion for the same day.
-- ---------------------------------------------------------------------------
CREATE TABLE routine_completions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    routine_id      UUID        NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    occurrence_date DATE        NOT NULL,
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (routine_id, occurrence_date)
);

-- ---------------------------------------------------------------------------
-- safety_audit_log
-- Append-only. Every deterministic gate decision and every semantic safety
-- review verdict is written here by application code (never by an agent).
-- architecture.md §13 — "Audit logging" requirement.
-- ---------------------------------------------------------------------------
CREATE TABLE safety_audit_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    routine_id          UUID        NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    stage               TEXT        NOT NULL CHECK (stage IN ('deterministic_gate', 'semantic_review')),
    decision            TEXT        NOT NULL CHECK (decision IN ('pass', 'block')),
    matched_categories  TEXT,
    detail              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- alerts
-- Created by application code when Maria taps "Help me".
-- The Escalation Agent may enrich category + message, but the row is always
-- created by deterministic code — the agent's participation is optional
-- (architecture.md §7.6, fail-open design).
-- ---------------------------------------------------------------------------
CREATE TABLE alerts (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    assisted_user_id UUID        NOT NULL REFERENCES assisted_users(id) ON DELETE CASCADE,
    caregiver_id     UUID        NOT NULL REFERENCES caregivers(id)     ON DELETE CASCADE,
    category         TEXT        NOT NULL,
    message          TEXT        NOT NULL,
    source_note      TEXT,
    status           TEXT        NOT NULL DEFAULT 'open'
                         CHECK (status IN ('open', 'acknowledged', 'resolved')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_at  TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Indexes
-- idx_routines_assisted_user_status: used by GET /internal/today to find
--   active routines for a specific assisted user efficiently.
-- idx_alerts_caregiver_status_date: used by GET /internal/alerts to list
--   open alerts for a caregiver, newest first. Includes created_at DESC
--   to support efficient ORDER BY.
-- idx_routine_completions_lookup: used by get_today_routines NOT EXISTS
--   subquery to check if a routine was completed on a given date.
-- ---------------------------------------------------------------------------
CREATE INDEX idx_routines_assisted_user_status
    ON routines(assisted_user_id, status);

CREATE INDEX idx_alerts_caregiver_status_date
    ON alerts(caregiver_id, status, created_at DESC);

CREATE INDEX idx_routine_completions_lookup
    ON routine_completions(routine_id, occurrence_date);
