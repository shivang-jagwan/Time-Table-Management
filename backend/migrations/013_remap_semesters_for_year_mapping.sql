-- Remap legacy semester numbers to match the new Year coverage mapping.
-- New convention:
--   Year 1 -> Sem 1–2 (use Sem 2)
--   Year 2 -> Sem 2–3 (use Sem 3)
--   Year 3 -> Sem 4–5 (use Sem 5)
--
-- This migration updates existing data that was previously stored under even semesters:
--   Sem 4 -> Sem 3
--   Sem 6 -> Sem 5
--
-- It also updates timetable_runs.parameters["semester"] when present.

BEGIN;

-- 1) Subjects / Sections (no uniqueness constraints on semester)
UPDATE subjects
SET semester = 3
WHERE semester = 4;

UPDATE subjects
SET semester = 5
WHERE semester = 6;

UPDATE sections
SET semester = 3
WHERE semester = 4;

UPDATE sections
SET semester = 5
WHERE semester = 6;

-- 2) Track subjects (has a uniqueness constraint including semester)
-- Drop rows that would conflict after remapping.
DELETE FROM track_subjects t4
USING track_subjects t3
WHERE t4.semester = 4
  AND t3.semester = 3
  AND t4.program_id = t3.program_id
  AND t4.track = t3.track
  AND t4.subject_id = t3.subject_id;

UPDATE track_subjects
SET semester = 3
WHERE semester = 4;

DELETE FROM track_subjects t6
USING track_subjects t5
WHERE t6.semester = 6
  AND t5.semester = 5
  AND t6.program_id = t5.program_id
  AND t6.track = t5.track
  AND t6.subject_id = t5.subject_id;

UPDATE track_subjects
SET semester = 5
WHERE semester = 6;

-- 3) Timetable run parameters (best-effort; leave rows without "semester" untouched)
UPDATE timetable_runs
SET parameters = jsonb_set(parameters, '{semester}', to_jsonb(3), true)
WHERE (parameters ? 'semester')
  AND NULLIF(parameters->>'semester', '') IS NOT NULL
  AND (parameters->>'semester')::int = 4;

UPDATE timetable_runs
SET parameters = jsonb_set(parameters, '{semester}', to_jsonb(5), true)
WHERE (parameters ? 'semester')
  AND NULLIF(parameters->>'semester', '') IS NOT NULL
  AND (parameters->>'semester')::int = 6;

-- 4) Cosmetic: update human-readable labels seeded as "Sem 6" to "Sem 5"
-- (Only affects names that literally include the substring.
--  Does not touch subject/section codes.)
UPDATE sections
SET name = replace(name, 'Sem 6', 'Sem 5')
WHERE semester = 5
  AND name LIKE '%Sem 6%';

UPDATE subjects
SET name = replace(name, 'Sem 6', 'Sem 5')
WHERE semester = 5
  AND name LIKE '%Sem 6%';

COMMIT;
