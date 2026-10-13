-- ─────────────────────────────────────────────────────────────────────────
-- bootstrap_shared_db.sql — one-time setup on the SHARED EC2 Postgres
--
-- Purpose: carve out an ISOLATED database + roles for the SDLC platform on the
-- existing (shared) Postgres instance, so it never touches the other apps that
-- live on the same server. Run ONCE, by a SUPERUSER, before `make migrate`.
--
-- Run it like:
--   psql "postgres://<superuser>:<pw>@<pg-host>:5432/postgres" -f bootstrap_shared_db.sql
--
-- What the app's own migrations still do for you (do NOT do these here):
--   • create the non-superuser app role `sdlc_app` + grants  (apps/tenancy/migrations/0002_rls.py)
--   • enable RLS + tenant-isolation policies on every table  (0002_rls.py)
--   • CREATE EXTENSION vector                                (apps/registry/migrations/0001_initial.py)
-- The migration role below is given CREATEROLE so 0002_rls.py can create sdlc_app.
-- The `vector` extension is pre-created here because pgvector is NOT a "trusted"
-- extension — only a superuser can CREATE it. Pre-creating makes the migration's
-- `CREATE EXTENSION IF NOT EXISTS vector` a harmless no-op under the non-superuser role.
-- ─────────────────────────────────────────────────────────────────────────

-- 1) Migration/owner role (privileged for THIS db only — NOT a cluster superuser).
--    Runs Django migrations (DDL) and, via 0002_rls.py, creates the app role.
--    >>> CHANGE THE PASSWORD before running. <<<
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sdlc_migrator') THEN
    CREATE ROLE sdlc_migrator LOGIN PASSWORD 'CHANGE_ME_migrator_pw' CREATEROLE;
  END IF;
END
$$;

-- 2) The isolated application database, owned by the migration role.
--    (CREATE DATABASE cannot run inside the DO block / a transaction, hence plain.)
--    If it already exists this errors harmlessly — comment it out on re-runs.
CREATE DATABASE sdlc_platform OWNER sdlc_migrator;

-- 3) Temporal's databases (Temporal's auto-setup expects to own these).
--    Only needed for Temporal Option T1 (self-hosted Temporal on the EC2 box).
--    Skip if you use Temporal Cloud (Option T2).
CREATE DATABASE temporal OWNER sdlc_migrator;
CREATE DATABASE temporal_visibility OWNER sdlc_migrator;

-- ── Now connect to the app DB and pre-create the vector extension (superuser only). ──
-- In psql this runs the rest against sdlc_platform:
\connect sdlc_platform
CREATE EXTENSION IF NOT EXISTS vector;

-- Let the migration role own the public schema so it can DDL freely (Postgres 15+
-- locks down public by default).
ALTER SCHEMA public OWNER TO sdlc_migrator;
GRANT ALL ON SCHEMA public TO sdlc_migrator;

-- Done. Next: point .env at this DB and run `make migrate` (as sdlc_migrator),
-- which creates the sdlc_app role, RLS policies, and all tables.
