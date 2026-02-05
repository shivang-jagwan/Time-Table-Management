-- Create `tenants` and add `tenant_id` to users.
-- Safe to run multiple times.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id uuid NULL;
CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users (tenant_id);

-- Drop legacy global-unique constraint/index on username so we can do (tenant_id, username).
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key;
DROP INDEX IF EXISTS ux_users_username;
DROP INDEX IF EXISTS users_username_key;

-- Enforce case-insensitive uniqueness per tenant.
-- (We keep this as a UNIQUE INDEX so it works without requiring citext.)
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tenant_username_ci
  ON users (tenant_id, lower(username));

COMMIT;
