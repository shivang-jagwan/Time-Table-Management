-- Make timetable_runs.academic_year_id nullable to support semester-global solver runs.
--
-- Old architecture: one run per (program_id, semester, academic_year_id)
-- New architecture: one run per (program_id, semester) spanning multiple academic years;
--                 per-entry year identity is stored in timetable_entries.academic_year_id.

ALTER TABLE timetable_runs
  ALTER COLUMN academic_year_id DROP NOT NULL;
