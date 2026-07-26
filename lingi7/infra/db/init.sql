-- ─────────────────────────────────────────────────────────────────────────────
-- Lingi7 — PostgreSQL Initialisation Script
-- Runs once on first container creation (docker-entrypoint-initdb.d)
--
-- Creates the isolated escrow_ledger schema and a restricted DB user
-- that has WRITE access only to that schema. This enforces at the
-- database level that only the escrow service can write ledger entries.
-- ─────────────────────────────────────────────────────────────────────────────

-- Create the isolated escrow ledger schema
CREATE SCHEMA IF NOT EXISTS escrow_ledger;

-- Create the restricted escrow DB user
-- In production, set the password via environment variable, not hardcoded here
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'lingi7_escrow') THEN
        CREATE ROLE lingi7_escrow LOGIN PASSWORD 'CHANGE_IN_PRODUCTION';
    END IF;
END
$$;

-- Grant the escrow user access only to the escrow_ledger schema
GRANT USAGE ON SCHEMA escrow_ledger TO lingi7_escrow;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA escrow_ledger TO lingi7_escrow;
-- Note: No UPDATE or DELETE — ledger entries are immutable
ALTER DEFAULT PRIVILEGES IN SCHEMA escrow_ledger
    GRANT SELECT, INSERT ON TABLES TO lingi7_escrow;

-- The main lingi7 application user has full access to the public schema
-- but no access to escrow_ledger (enforced at application level too)
GRANT ALL PRIVILEGES ON SCHEMA public TO lingi7;

COMMENT ON SCHEMA escrow_ledger IS
    'Isolated double-entry escrow ledger. Only the escrow service user may write here.';
