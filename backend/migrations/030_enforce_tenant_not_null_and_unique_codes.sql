-- Enforce strict per-tenant isolation at the DB level.
--
-- Goals:
-- 1) Prevent orphaned rows by requiring tenant_id (NOT NULL) on tenant-scoped tables.
-- 2) Ensure codes are unique per tenant (composite unique), not globally.
--
-- NOTE:
-- This migration intentionally makes the schema incompatible with "shared" mode (tenant_id IS NULL).
-- It is intended for TENANT_MODE=per_tenant deployments.

BEGIN;

-- Ensure the default tenant exists (used to backfill legacy rows).
INSERT INTO tenants (slug, name)
SELECT 'default', 'Default College'
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'default');

DO $$
DECLARE
    default_tenant_id uuid;
    t text;
BEGIN
    SELECT id INTO default_tenant_id FROM tenants WHERE slug = 'default' LIMIT 1;
    IF default_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Default tenant could not be created/found';
    END IF;

    -- Backfill + enforce NOT NULL for all tenant-scoped tables.
    FOREACH t IN ARRAY ARRAY[
        'users',
        'programs',
        'rooms',
        'teachers',
        'subjects',
        'sections',
        'academic_years',
        'time_slots',
        'timetable_runs',
        'timetable_entries',
        'timetable_conflicts',
        'fixed_timetable_entries',
        'special_allotments',
        'track_subjects',
        'section_subjects',
        'section_time_windows',
        'section_breaks',
        'teacher_subject_sections',
        'teacher_subjects',
        'teacher_subject_years',
        'section_electives',
        'section_elective_blocks',
        'elective_blocks',
        'elective_block_subjects',
        'combined_subject_groups',
        'combined_subject_sections'
    ]
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('UPDATE %I SET tenant_id = $1 WHERE tenant_id IS NULL', t)
                USING default_tenant_id;
            EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id SET NOT NULL', t);
        END IF;
    END LOOP;
END $$;

-- Pre-flight checks: abort with a clear error if any tenant already has duplicates.
DO $$
BEGIN
    IF to_regclass('public.programs') IS NOT NULL AND EXISTS (
        SELECT 1 FROM programs GROUP BY tenant_id, code HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate programs.code within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.rooms') IS NOT NULL AND EXISTS (
        SELECT 1 FROM rooms GROUP BY tenant_id, code HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate rooms.code within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.teachers') IS NOT NULL AND EXISTS (
        SELECT 1 FROM teachers GROUP BY tenant_id, code HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate teachers.code within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.subjects') IS NOT NULL AND EXISTS (
        SELECT 1 FROM subjects GROUP BY tenant_id, code HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate subjects.code within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.sections') IS NOT NULL AND EXISTS (
        SELECT 1 FROM sections GROUP BY tenant_id, code HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate sections.code within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.academic_years') IS NOT NULL AND EXISTS (
        SELECT 1 FROM academic_years GROUP BY tenant_id, year_number HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate academic_years.year_number within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;

    IF to_regclass('public.time_slots') IS NOT NULL AND EXISTS (
        SELECT 1 FROM time_slots GROUP BY tenant_id, day_of_week, slot_index HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate time_slots (day_of_week, slot_index) within a tenant detected; resolve duplicates before enforcing uniqueness.';
    END IF;
END $$;

-- Replace shared/per-tenant partial unique indexes with strict per-tenant composite uniqueness.

-- programs.code
DROP INDEX IF EXISTS ux_programs_code_shared;
DROP INDEX IF EXISTS ux_programs_tenant_code;
ALTER TABLE programs DROP CONSTRAINT IF EXISTS programs_code_key;
DROP INDEX IF EXISTS programs_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_programs_tenant_code ON programs (tenant_id, code);

-- rooms.code
DROP INDEX IF EXISTS ux_rooms_code_shared;
DROP INDEX IF EXISTS ux_rooms_tenant_code;
ALTER TABLE rooms DROP CONSTRAINT IF EXISTS rooms_code_key;
DROP INDEX IF EXISTS rooms_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_rooms_tenant_code ON rooms (tenant_id, code);

-- teachers.code
DROP INDEX IF EXISTS ux_teachers_code_shared;
DROP INDEX IF EXISTS ux_teachers_tenant_code;
ALTER TABLE teachers DROP CONSTRAINT IF EXISTS teachers_code_key;
DROP INDEX IF EXISTS teachers_code_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_teachers_tenant_code ON teachers (tenant_id, code);

-- subjects.code
DROP INDEX IF EXISTS ux_subjects_tenant_code;
CREATE UNIQUE INDEX IF NOT EXISTS ux_subjects_tenant_code ON subjects (tenant_id, code);

-- sections.code
DROP INDEX IF EXISTS ux_sections_tenant_code;
CREATE UNIQUE INDEX IF NOT EXISTS ux_sections_tenant_code ON sections (tenant_id, code);

-- academic_years.year_number
DROP INDEX IF EXISTS ux_academic_years_year_shared;
DROP INDEX IF EXISTS ux_academic_years_tenant_year;
ALTER TABLE academic_years DROP CONSTRAINT IF EXISTS academic_years_year_number_key;
ALTER TABLE academic_years DROP CONSTRAINT IF EXISTS ux_academic_years_year_number;
DROP INDEX IF EXISTS academic_years_year_number_key;
CREATE UNIQUE INDEX IF NOT EXISTS ux_academic_years_tenant_year ON academic_years (tenant_id, year_number);

-- time_slots uniqueness
DROP INDEX IF EXISTS ux_time_slots_day_slot_shared;
DROP INDEX IF EXISTS ux_time_slots_tenant_day_slot;
DROP INDEX IF EXISTS ux_time_slots_day_slot;
CREATE UNIQUE INDEX IF NOT EXISTS ux_time_slots_tenant_day_slot ON time_slots (tenant_id, day_of_week, slot_index);

COMMIT;
