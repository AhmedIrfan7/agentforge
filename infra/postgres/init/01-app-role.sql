-- Runs once, only on first container creation (empty data dir), via
-- Postgres's /docker-entrypoint-initdb.d/ convention.
--
-- POSTGRES_USER (the bootstrap role, e.g. "agentforge") is ALWAYS a
-- Postgres superuser — that's fixed behavior of the official image, not
-- something docker-compose env vars can change. Superusers bypass Row-
-- Level Security unconditionally, even on tables with FORCE ROW LEVEL
-- SECURITY (see docs/adr/0003-multi-tenancy-isolation-strategy.md).
--
-- So: migrations run as the bootstrap superuser (needs DDL rights anyway),
-- but the application's runtime connections use this separate, deliberately
-- unprivileged role instead — it has no BYPASSRLS, isn't a superuser, and
-- isn't a table owner, so RLS policies actually apply to it.

CREATE ROLE agentforge_app WITH LOGIN PASSWORD 'agentforge_app';

GRANT CONNECT ON DATABASE agentforge TO agentforge_app;
GRANT USAGE ON SCHEMA public TO agentforge_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentforge_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agentforge_app;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agentforge_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO agentforge_app;
