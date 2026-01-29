BEGIN;

-- =========================================================
-- Year-only timetabling
--
-- Removes the "semester" concept across core tables.
-- The product now operates purely by Academic Year.
-- =========================================================

-- -------------------------
-- Sections
-- -------------------------
ALTER TABLE sections
  DROP CONSTRAINT IF EXISTS ck_sections_semester;

ALTER TABLE sections
  DROP COLUMN IF EXISTS semester;

-- -------------------------
-- Subjects
-- -------------------------
ALTER TABLE subjects
  DROP CONSTRAINT IF EXISTS ck_subjects_semester;

DROP INDEX IF EXISTS ix_subjects_year_semester;

ALTER TABLE subjects
  DROP COLUMN IF EXISTS semester;

-- -------------------------
-- Track curriculum: track_subjects
-- Previously keyed by (program_id, semester, track, subject_id)
-- Now keyed by (program_id, academic_year_id, track, subject_id)
-- -------------------------
ALTER TABLE track_subjects
  ADD COLUMN IF NOT EXISTS academic_year_id uuid NULL REFERENCES academic_years(id) ON DELETE RESTRICT;

-- Backfill academic_year_id using subject_id
UPDATE track_subjects ts
SET academic_year_id = s.academic_year_id
FROM subjects s
WHERE ts.academic_year_id IS NULL
  AND ts.subject_id = s.id;

-- If any rows are still NULL (dangling subject_id), drop them to keep constraints consistent
DELETE FROM track_subjects
WHERE academic_year_id IS NULL;

-- Drop legacy constraints / indexes
ALTER TABLE track_subjects
  DROP CONSTRAINT IF EXISTS uq_track_subjects;

ALTER TABLE track_subjects
  DROP CONSTRAINT IF EXISTS ck_track_subjects_semester;

DROP INDEX IF EXISTS idx_track_subjects_lookup;

-- Drop the semester column after backfill
ALTER TABLE track_subjects
  DROP COLUMN IF EXISTS semester;

-- Enforce non-null year
ALTER TABLE track_subjects
  ALTER COLUMN academic_year_id SET NOT NULL;

-- New lookup index + uniqueness
CREATE INDEX IF NOT EXISTS idx_track_subjects_lookup_year
  ON track_subjects(program_id, academic_year_id, track);

CREATE UNIQUE INDEX IF NOT EXISTS ux_track_subjects_program_year_track_subject
  ON track_subjects(program_id, academic_year_id, track, subject_id);

-- -------------------------
-- Elective blocks
-- -------------------------
DROP INDEX IF EXISTS ix_elective_blocks_program_year_semester;
DROP INDEX IF EXISTS ux_elective_blocks_program_year_semester_name;

ALTER TABLE elective_blocks
  DROP CONSTRAINT IF EXISTS ck_elective_blocks_semester;

ALTER TABLE elective_blocks
  DROP COLUMN IF EXISTS semester;

CREATE INDEX IF NOT EXISTS ix_elective_blocks_program_year
  ON elective_blocks(program_id, academic_year_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_elective_blocks_program_year_name
  ON elective_blocks(program_id, academic_year_id, name);

-- -------------------------
-- Timetable run parameters cleanup (JSON)
-- -------------------------
UPDATE timetable_runs
SET parameters = parameters - 'semester'
WHERE parameters ? 'semester';

UPDATE timetable_runs
SET parameters = parameters - 'semesters'
WHERE parameters ? 'semesters';

COMMIT;
