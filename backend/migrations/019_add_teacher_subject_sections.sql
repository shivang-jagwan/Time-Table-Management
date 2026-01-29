-- Teacher is assigned to Subject + Specific Sections.
-- Replaces eligibility tables (teacher_subjects / teacher_subject_years).

BEGIN;

CREATE TABLE IF NOT EXISTS teacher_subject_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_teacher_subject_section UNIQUE (teacher_id, subject_id, section_id)
);

-- Enforce exactly one active teacher per (section, subject)
CREATE UNIQUE INDEX IF NOT EXISTS uq_teacher_subject_sections_active_section_subject
  ON teacher_subject_sections(section_id, subject_id)
  WHERE is_active IS TRUE;

CREATE INDEX IF NOT EXISTS ix_teacher_subject_sections_teacher
  ON teacher_subject_sections(teacher_id);

CREATE INDEX IF NOT EXISTS ix_teacher_subject_sections_subject
  ON teacher_subject_sections(subject_id);

CREATE INDEX IF NOT EXISTS ix_teacher_subject_sections_section
  ON teacher_subject_sections(section_id);

-- Drop legacy eligibility tables (no longer used).
DROP TABLE IF EXISTS teacher_subject_years;
DROP TABLE IF EXISTS teacher_subjects;

COMMIT;
