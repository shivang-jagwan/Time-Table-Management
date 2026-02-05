-- Tenant-scope academic_years and time_slots.
-- Safe to run multiple times.
--
-- Notes:
-- - We do not attempt to rewrite existing FK constraints; scoping is enforced at the app layer.
-- - In shared mode, tenant_id remains NULL.

BEGIN;

ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS tenant_id uuid NULL;
CREATE INDEX IF NOT EXISTS ix_academic_years_tenant_id ON academic_years (tenant_id);

-- Replace global uniqueness with partial indexes to support shared/per-tenant modes.
ALTER TABLE academic_years DROP CONSTRAINT IF EXISTS ux_academic_years_year_number;
ALTER TABLE academic_years DROP CONSTRAINT IF EXISTS academic_years_year_number_key;
DROP INDEX IF EXISTS academic_years_year_number_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_academic_years_year_shared
  ON academic_years (year_number)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_academic_years_tenant_year
  ON academic_years (tenant_id, year_number)
  WHERE tenant_id IS NOT NULL;


ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS tenant_id uuid NULL;
CREATE INDEX IF NOT EXISTS ix_time_slots_tenant_id ON time_slots (tenant_id);

-- Replace global uniqueness with partial indexes to support shared/per-tenant modes.
DROP INDEX IF EXISTS ux_time_slots_day_slot;

CREATE UNIQUE INDEX IF NOT EXISTS ux_time_slots_day_slot_shared
  ON time_slots (day_of_week, slot_index)
  WHERE tenant_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_time_slots_tenant_day_slot
  ON time_slots (tenant_id, day_of_week, slot_index)
  WHERE tenant_id IS NOT NULL;

COMMIT;
