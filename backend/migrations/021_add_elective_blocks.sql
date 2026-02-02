BEGIN;

-- =========================================================
-- Elective Blocks (Parallel Electives)
--
-- Supports scheduling multiple elective subjects in the same section+slot
-- as a single "block event" while keeping normal classes unique per slot.
-- =========================================================

CREATE TABLE IF NOT EXISTS elective_blocks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  program_id uuid NOT NULL REFERENCES programs(id) ON DELETE RESTRICT,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
  name text NOT NULL,
  code text NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_elective_blocks_program_year
  ON elective_blocks(program_id, academic_year_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_elective_blocks_program_year_name
  ON elective_blocks(program_id, academic_year_id, name);

CREATE TABLE IF NOT EXISTS elective_block_subjects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  block_id uuid NOT NULL REFERENCES elective_blocks(id) ON DELETE CASCADE,
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_elective_block_subjects_block_subject UNIQUE (block_id, subject_id),
  CONSTRAINT uq_elective_block_subjects_block_teacher UNIQUE (block_id, teacher_id)
);

CREATE INDEX IF NOT EXISTS ix_elective_block_subjects_block
  ON elective_block_subjects(block_id);
CREATE INDEX IF NOT EXISTS ix_elective_block_subjects_subject
  ON elective_block_subjects(subject_id);
CREATE INDEX IF NOT EXISTS ix_elective_block_subjects_teacher
  ON elective_block_subjects(teacher_id);

CREATE TABLE IF NOT EXISTS section_elective_blocks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  section_id uuid NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
  block_id uuid NOT NULL REFERENCES elective_blocks(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_section_elective_blocks_section_block UNIQUE (section_id, block_id)
);

CREATE INDEX IF NOT EXISTS ix_section_elective_blocks_section
  ON section_elective_blocks(section_id);
CREATE INDEX IF NOT EXISTS ix_section_elective_blocks_block
  ON section_elective_blocks(block_id);

-- =========================================================
-- Timetable entries: group parallel elective entries by elective_block_id
-- =========================================================

ALTER TABLE timetable_entries
  ADD COLUMN IF NOT EXISTS elective_block_id uuid NULL REFERENCES elective_blocks(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_entries_elective_block
  ON timetable_entries(elective_block_id);

-- =========================================================
-- Allow multiple entries per (run, section, slot) ONLY for electives.
-- Keep original uniqueness for non-elective entries.
-- =========================================================

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ux_entries_run_section_slot'
  ) THEN
    ALTER TABLE timetable_entries DROP CONSTRAINT ux_entries_run_section_slot;
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_entries_run_section_slot_non_elective
  ON timetable_entries(run_id, section_id, slot_id)
  WHERE elective_block_id IS NULL;

COMMIT;
