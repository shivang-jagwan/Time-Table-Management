-- Add tenant scoping support to core configuration tables.
-- Safe to run multiple times.
--
-- Tenant model:
-- - shared mode: tenant_id is NULL (single global dataset)
-- - per_user mode: tenant_id is NOT NULL (rows scoped per admin)
--
-- Uniqueness:
-- - programs.code, rooms.code, teachers.code are unique in shared mode
-- - in per_user mode, uniqueness is (tenant_id, code)

BEGIN;

-- 1) Add tenant_id columns + basic indexes
ALTER TABLE programs ADD COLUMN IF NOT EXISTS tenant_id uuid;
CREATE INDEX IF NOT EXISTS ix_programs_tenant_id ON programs (tenant_id);

ALTER TABLE rooms ADD COLUMN IF NOT EXISTS tenant_id uuid;
CREATE INDEX IF NOT EXISTS ix_rooms_tenant_id ON rooms (tenant_id);

ALTER TABLE teachers ADD COLUMN IF NOT EXISTS tenant_id uuid;
CREATE INDEX IF NOT EXISTS ix_teachers_tenant_id ON teachers (tenant_id);

ALTER TABLE subjects ADD COLUMN IF NOT EXISTS tenant_id uuid;
CREATE INDEX IF NOT EXISTS ix_subjects_tenant_id ON subjects (tenant_id);

ALTER TABLE sections ADD COLUMN IF NOT EXISTS tenant_id uuid;
CREATE INDEX IF NOT EXISTS ix_sections_tenant_id ON sections (tenant_id);

-- 2) Replace global UNIQUE(code) with partial unique indexes that support both modes.
-- Programs
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_code_key;
DROP INDEX IF EXISTS programs_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_programs_code_shared
  ON programs (code)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_programs_tenant_code
  ON programs (tenant_id, code)
  WHERE tenant_id IS NOT NULL;

-- Rooms
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_code_key;
DROP INDEX IF EXISTS rooms_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_rooms_code_shared
  ON rooms (code)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_rooms_tenant_code
  ON rooms (tenant_id, code)
  WHERE tenant_id IS NOT NULL;

-- Teachers
ALTER TABLE teachers DROP CONSTRAINT IF EXISTS teachers_code_key;
DROP INDEX IF EXISTS teachers_code_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_teachers_code_shared
  ON teachers (code)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_teachers_tenant_code
  ON teachers (tenant_id, code)
  WHERE tenant_id IS NOT NULL;

COMMIT;
