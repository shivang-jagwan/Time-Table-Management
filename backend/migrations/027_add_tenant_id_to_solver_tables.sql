-- Add tenant scoping to solver/admin-generated tables.
-- Safe to run multiple times.
--
-- Shared mode: tenant_id IS NULL
-- Per-user mode: tenant_id IS NOT NULL

BEGIN;

-- Some deployments may not have all tables (depending on which historical migrations ran).
-- Guard each table so this migration can run safely across environments.
DO $$
DECLARE
	t text;
	idx text;
BEGIN
	FOREACH t IN ARRAY ARRAY[
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
		-- legacy
		'teacher_subjects',
		-- newer
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
			EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id uuid', t);
			idx := 'ix_' || t || '_tenant_id';
			EXECUTE format('CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)', idx, t);
		END IF;
	END LOOP;
END $$;

COMMIT;
