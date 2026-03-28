-- 040_add_duration_slots_columns.sql
-- Introduce dedicated duration_slots columns while preserving legacy
-- lab_block_size_slots compatibility for existing scripts and APIs.

BEGIN;

ALTER TABLE IF EXISTS subjects
  ADD COLUMN IF NOT EXISTS duration_slots INTEGER;

ALTER TABLE IF EXISTS curriculum_subjects
  ADD COLUMN IF NOT EXISTS duration_slots INTEGER;

-- Backfill the new columns from legacy values.
UPDATE subjects
SET duration_slots = GREATEST(COALESCE(duration_slots, lab_block_size_slots, 1), 1)
WHERE duration_slots IS NULL
   OR duration_slots <> GREATEST(COALESCE(lab_block_size_slots, 1), 1);

UPDATE curriculum_subjects
SET duration_slots = GREATEST(COALESCE(duration_slots, lab_block_size_slots, 1), 1)
WHERE duration_slots IS NULL
   OR duration_slots <> GREATEST(COALESCE(lab_block_size_slots, 1), 1);

-- Normalize legacy mirror values once during migration.
UPDATE subjects
SET lab_block_size_slots = duration_slots
WHERE lab_block_size_slots IS DISTINCT FROM duration_slots;

UPDATE curriculum_subjects
SET lab_block_size_slots = duration_slots
WHERE lab_block_size_slots IS DISTINCT FROM duration_slots;

-- Keep legacy and new duration columns in sync for all future writes.
CREATE OR REPLACE FUNCTION sync_duration_slots_with_legacy()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    duration_changed BOOLEAN := FALSE;
    legacy_changed BOOLEAN := FALSE;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        duration_changed := NEW.duration_slots IS DISTINCT FROM OLD.duration_slots;
        legacy_changed := NEW.lab_block_size_slots IS DISTINCT FROM OLD.lab_block_size_slots;

        IF duration_changed AND NOT legacy_changed THEN
            NEW.lab_block_size_slots := NEW.duration_slots;
        ELSIF legacy_changed AND NOT duration_changed THEN
            NEW.duration_slots := NEW.lab_block_size_slots;
        ELSIF duration_changed AND legacy_changed AND NEW.duration_slots IS DISTINCT FROM NEW.lab_block_size_slots THEN
            NEW.lab_block_size_slots := NEW.duration_slots;
        END IF;
    ELSE
        IF NEW.duration_slots IS NULL AND NEW.lab_block_size_slots IS NULL THEN
            NEW.duration_slots := 1;
            NEW.lab_block_size_slots := 1;
        ELSIF NEW.duration_slots IS NULL THEN
            NEW.duration_slots := NEW.lab_block_size_slots;
        ELSIF NEW.lab_block_size_slots IS NULL THEN
            NEW.lab_block_size_slots := NEW.duration_slots;
        ELSIF NEW.duration_slots IS DISTINCT FROM NEW.lab_block_size_slots THEN
        IF int4(NEW.duration_slots) = 1 AND int4(NEW.lab_block_size_slots) <> 1 THEN
          NEW.duration_slots := NEW.lab_block_size_slots;
        ELSIF int4(NEW.lab_block_size_slots) = 1 AND int4(NEW.duration_slots) <> 1 THEN
          NEW.lab_block_size_slots := NEW.duration_slots;
        ELSE
          NEW.lab_block_size_slots := NEW.duration_slots;
        END IF;
        END IF;
    END IF;

    NEW.duration_slots := GREATEST(COALESCE(NEW.duration_slots, 1), 1);
    NEW.lab_block_size_slots := GREATEST(COALESCE(NEW.lab_block_size_slots, NEW.duration_slots, 1), 1);
    NEW.lab_block_size_slots := NEW.duration_slots;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_subjects_sync_duration_slots ON subjects;
CREATE TRIGGER trg_subjects_sync_duration_slots
BEFORE INSERT OR UPDATE ON subjects
FOR EACH ROW
EXECUTE FUNCTION sync_duration_slots_with_legacy();

DROP TRIGGER IF EXISTS trg_curriculum_subjects_sync_duration_slots ON curriculum_subjects;
CREATE TRIGGER trg_curriculum_subjects_sync_duration_slots
BEFORE INSERT OR UPDATE ON curriculum_subjects
FOR EACH ROW
EXECUTE FUNCTION sync_duration_slots_with_legacy();

ALTER TABLE subjects
  ALTER COLUMN duration_slots SET NOT NULL;

ALTER TABLE curriculum_subjects
  ALTER COLUMN duration_slots SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_subjects_duration_slots'
  ) THEN
    ALTER TABLE subjects
      ADD CONSTRAINT ck_subjects_duration_slots CHECK (duration_slots >= 1);
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ck_curriculum_subjects_duration_slots'
  ) THEN
    ALTER TABLE curriculum_subjects
      ADD CONSTRAINT ck_curriculum_subjects_duration_slots CHECK (duration_slots >= 1);
  END IF;
END $$;

-- Refresh compat view with explicit duration_slots.
CREATE OR REPLACE VIEW v_subject_curriculum AS
SELECT
    s.id                    AS subject_id,
    s.tenant_id,
    s.program_id,
    s.academic_year_id,
    s.code                  AS subject_code,
    s.name                  AS subject_name,
    s.subject_type,
    s.credits,
    cs.id                   AS curriculum_id,
    cs.track,
    cs.sessions_per_week,
    cs.max_per_day,
    cs.lab_block_size_slots,
    cs.is_elective,
    COALESCE(cs.duration_slots, cs.lab_block_size_slots, 1) AS duration_slots
FROM subjects s
LEFT JOIN curriculum_subjects cs
    ON cs.subject_id = s.id
    AND cs.tenant_id = s.tenant_id
    AND cs.program_id = s.program_id
    AND cs.academic_year_id = s.academic_year_id;

COMMIT;
