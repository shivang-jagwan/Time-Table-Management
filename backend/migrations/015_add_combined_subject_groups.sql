BEGIN;

-- =========================================================
-- Combined Classes (Strict Combined Subject Groups)
--
-- A combined group is scoped to (academic_year_id, subject_id) and contains 2+ sections.
-- Solver will schedule ALL sessions of that subject together for those sections.
-- =========================================================

CREATE TABLE IF NOT EXISTS combined_subject_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_combined_subject_groups_year_subject UNIQUE (academic_year_id, subject_id)
);

CREATE INDEX IF NOT EXISTS ix_combined_subject_groups_year ON combined_subject_groups(academic_year_id);
CREATE INDEX IF NOT EXISTS ix_combined_subject_groups_subject ON combined_subject_groups(subject_id);

CREATE TABLE IF NOT EXISTS combined_subject_sections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  combined_group_id uuid NOT NULL REFERENCES combined_subject_groups(id) ON DELETE CASCADE,
  section_id uuid NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_combined_subject_sections_group_section UNIQUE (combined_group_id, section_id)
);

CREATE INDEX IF NOT EXISTS ix_combined_subject_sections_group ON combined_subject_sections(combined_group_id);
CREATE INDEX IF NOT EXISTS ix_combined_subject_sections_section ON combined_subject_sections(section_id);

-- =========================================================
-- Timetable entries room-slot uniqueness adjustment
--
-- Combined classes produce multiple timetable_entries with the same (run_id, room_id, slot_id)
-- (one per section), which violates the original uniqueness constraint.
--
-- New rule:
-- - Enforce unique (run_id, room_id, slot_id) ONLY for non-combined entries.
-- - Combined entries (combined_class_id IS NOT NULL) may share room+slot.
-- =========================================================

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ux_entries_run_room_slot'
  ) THEN
    ALTER TABLE timetable_entries DROP CONSTRAINT ux_entries_run_room_slot;
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_entries_run_room_slot_uncombined
  ON timetable_entries(run_id, room_id, slot_id)
  WHERE combined_class_id IS NULL;

COMMIT;
