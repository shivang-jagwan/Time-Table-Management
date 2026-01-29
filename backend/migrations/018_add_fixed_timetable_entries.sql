-- Hard-fixed timetable entries (manual locks) enforced as solver hard constraints.

BEGIN;

CREATE TABLE IF NOT EXISTS fixed_timetable_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    room_id uuid NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    slot_id uuid NOT NULL REFERENCES time_slots(id) ON DELETE RESTRICT,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Only one *active* fixed entry per (section, slot)
CREATE UNIQUE INDEX IF NOT EXISTS ux_fixed_entries_section_slot_active
  ON fixed_timetable_entries(section_id, slot_id)
  WHERE is_active;

CREATE INDEX IF NOT EXISTS ix_fixed_entries_section_active
  ON fixed_timetable_entries(section_id, is_active);

CREATE INDEX IF NOT EXISTS ix_fixed_entries_slot_active
  ON fixed_timetable_entries(slot_id, is_active);

COMMIT;
