-- Special allotments (hard locked events) enforced as pre-solve occupied slots.

BEGIN;

CREATE TABLE IF NOT EXISTS special_allotments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    room_id uuid NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    slot_id uuid NOT NULL REFERENCES time_slots(id) ON DELETE RESTRICT,
    reason text NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Only one *active* special allotment per (section, slot)
CREATE UNIQUE INDEX IF NOT EXISTS ux_special_allotments_section_slot_active
  ON special_allotments(section_id, slot_id)
  WHERE is_active;

-- Only one *active* special allotment per (teacher, slot)
CREATE UNIQUE INDEX IF NOT EXISTS ux_special_allotments_teacher_slot_active
  ON special_allotments(teacher_id, slot_id)
  WHERE is_active;

-- Only one *active* special allotment per (room, slot)
CREATE UNIQUE INDEX IF NOT EXISTS ux_special_allotments_room_slot_active
  ON special_allotments(room_id, slot_id)
  WHERE is_active;

CREATE INDEX IF NOT EXISTS ix_special_allotments_section_active
  ON special_allotments(section_id, is_active);

CREATE INDEX IF NOT EXISTS ix_special_allotments_slot_active
  ON special_allotments(slot_id, is_active);

COMMIT;
