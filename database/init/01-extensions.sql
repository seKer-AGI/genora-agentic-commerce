-- Executed once by the postgres container on first start.
-- Extensions are also created by the Alembic migration (idempotent), so
-- databases provisioned without this script still work.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

-- Separate database used by the automated test-suite.
SELECT 'CREATE DATABASE genora_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'genora_test')\gexec
\connect genora_test
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
