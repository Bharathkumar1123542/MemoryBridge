-- MemoryBridge — demo seed data
-- Run AFTER 0001_init.sql:
--   psql "$DATABASE_URL" -f db/seed.sql
--
-- Creates:
--   Caregiver:      demo@memorybridge.app / demo1234
--   Assisted user:  Maria (linked to the caregiver above)
--
-- The password hash below is bcrypt(cost=12) of "demo1234".
-- Generate a fresh hash for production:
--   python3 -c "import bcrypt; print(bcrypt.hashpw(b'demo1234', bcrypt.gensalt(12)).decode())"
--
-- NEVER use this seed file against a production database.

-- Use a fixed UUID so the seed is idempotent (safe to re-run).
DO $$
DECLARE
    v_caregiver_id    UUID := '00000000-0000-0000-0000-000000000001';
    v_assisted_user_id UUID := '00000000-0000-0000-0000-000000000002';
BEGIN

    -- -----------------------------------------------------------------------
    -- Caregiver
    -- -----------------------------------------------------------------------
    INSERT INTO caregivers (id, name, email, password_hash)
    VALUES (
        v_caregiver_id,
        'Demo Caregiver',
        'demo@memorybridge.app',
        -- bcrypt(cost=12) of "demo1234"
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4oHqwCmG4e'
    )
    ON CONFLICT (id) DO NOTHING;

    -- -----------------------------------------------------------------------
    -- Assisted user — "Maria"
    -- Timezone defaults to UTC here; update to match your local demo timezone
    -- (e.g. 'America/Los_Angeles') so "today's routines" resolve correctly.
    -- -----------------------------------------------------------------------
    INSERT INTO assisted_users (id, caregiver_id, name, timezone)
    VALUES (
        v_assisted_user_id,
        v_caregiver_id,
        'Maria',
        'UTC'
    )
    ON CONFLICT (id) DO NOTHING;

END $$;
