BEGIN;

-- Align teachers table to backend model (Teacher.full_name/email/phone)
DO $$ BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='teachers' AND column_name='name'
    ) THEN
        ALTER TABLE teachers RENAME COLUMN name TO full_name;
    END IF;
END $$;

ALTER TABLE teachers
    ADD COLUMN IF NOT EXISTS email text,
    ADD COLUMN IF NOT EXISTS phone text;

-- Align timetable_runs table to backend model
ALTER TABLE timetable_runs
    ADD COLUMN IF NOT EXISTS seed integer,
    ADD COLUMN IF NOT EXISTS solver_version text,
    ADD COLUMN IF NOT EXISTS parameters jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Align timetable_entries table to backend model
ALTER TABLE timetable_entries
    ADD COLUMN IF NOT EXISTS combined_class_id uuid;

COMMIT;
