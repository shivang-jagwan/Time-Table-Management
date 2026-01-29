-- Upgrade: make teacher eligibility year-aware.
--
-- Replaces legacy global table:
--   teacher_subjects(teacher_id, subject_id)
-- with year-scoped:
--   teacher_subject_years(teacher_id, subject_id, academic_year_id)
--
-- Backfill rule (non-copying):
--   Each legacy (teacher_id, subject_id) is migrated to the subject's academic_year_id.
--   This does NOT copy eligibility across years.

BEGIN;

-- 1) New table
CREATE TABLE IF NOT EXISTS teacher_subject_years (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_teacher_subject_year UNIQUE (teacher_id, subject_id, academic_year_id)
);

CREATE INDEX IF NOT EXISTS ix_teacher_subject_years_subject ON teacher_subject_years(subject_id);
CREATE INDEX IF NOT EXISTS ix_teacher_subject_years_teacher ON teacher_subject_years(teacher_id);
CREATE INDEX IF NOT EXISTS ix_teacher_subject_years_year ON teacher_subject_years(academic_year_id);

-- 2) Backfill from legacy table if it exists
DO $$
BEGIN
  IF to_regclass('public.teacher_subjects') IS NOT NULL THEN
    INSERT INTO teacher_subject_years (teacher_id, subject_id, academic_year_id)
    SELECT ts.teacher_id, ts.subject_id, s.academic_year_id
    FROM teacher_subjects ts
    JOIN subjects s ON s.id = ts.subject_id
    ON CONFLICT (teacher_id, subject_id, academic_year_id) DO NOTHING;

    DROP TABLE teacher_subjects;
  END IF;
END $$;

COMMIT;
