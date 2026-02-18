BEGIN;

-- =========================================================
-- Upgrade elective blocks to allow multiple teachers/groups
-- per subject within the same block (subject+teacher pairs)
-- and migrate legacy section_electives into single-subject
-- elective blocks, then drop section_electives.
-- =========================================================

-- 1) Allow multiple rows per (block_id, subject_id) by changing uniqueness
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_elective_block_subjects_block_subject'
  ) THEN
    ALTER TABLE elective_block_subjects DROP CONSTRAINT uq_elective_block_subjects_block_subject;
  END IF;
EXCEPTION
  WHEN undefined_table THEN
    -- Table doesn't exist yet; ignore.
    NULL;
END $$;

-- New uniqueness: exact (block, subject, teacher) row
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'elective_block_subjects'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_constraint WHERE conname = 'uq_elective_block_subjects_block_subject_teacher'
    ) THEN
      ALTER TABLE elective_block_subjects
        ADD CONSTRAINT uq_elective_block_subjects_block_subject_teacher
        UNIQUE (block_id, subject_id, teacher_id);
    END IF;
  END IF;
END $$;

-- 2) Backup legacy table (if present)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'section_electives'
  ) THEN
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.tables
      WHERE table_name = 'section_electives_backup'
    ) THEN
      EXECUTE 'CREATE TABLE section_electives_backup AS TABLE section_electives WITH DATA';
    END IF;
  END IF;
END $$;

-- 3) Convert legacy section_electives into elective blocks
-- One block per (section, subject) selection.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'section_electives'
  ) THEN
    -- Materialize so the generated block_id is stable across inserts.
    CREATE TEMP TABLE IF NOT EXISTS tmp_legacy_section_electives_conv (
      section_id uuid,
      subject_id uuid,
      program_id uuid,
      academic_year_id uuid,
      tenant_id uuid,
      section_code text,
      block_id uuid,
      teacher_id uuid
    ) ON COMMIT DROP;

    TRUNCATE TABLE tmp_legacy_section_electives_conv;

    INSERT INTO tmp_legacy_section_electives_conv (
      section_id,
      subject_id,
      program_id,
      academic_year_id,
      tenant_id,
      section_code,
      block_id,
      teacher_id
    )
    SELECT
      e.section_id,
      e.subject_id,
      s.program_id,
      s.academic_year_id,
      s.tenant_id,
      s.code AS section_code,
      gen_random_uuid() AS block_id,
      (
        SELECT MIN(tss.teacher_id)
        FROM teacher_subject_sections tss
        WHERE tss.section_id = e.section_id
          AND tss.subject_id = e.subject_id
          AND tss.is_active = true
      ) AS teacher_id
    FROM section_electives e
    JOIN sections s ON s.id = e.section_id;

    INSERT INTO elective_blocks (id, tenant_id, program_id, academic_year_id, name, code, is_active)
    SELECT
      l.block_id,
      l.tenant_id,
      l.program_id,
      l.academic_year_id,
      ('Legacy Elective (' || l.section_code || ')')::text,
      ('LEGACY_' || l.section_code)::text,
      true
    FROM tmp_legacy_section_electives_conv l
    ON CONFLICT DO NOTHING;

    INSERT INTO section_elective_blocks (tenant_id, section_id, block_id)
    SELECT l.tenant_id, l.section_id, l.block_id
    FROM tmp_legacy_section_electives_conv l
    ON CONFLICT DO NOTHING;

    INSERT INTO elective_block_subjects (tenant_id, block_id, subject_id, teacher_id)
    SELECT l.tenant_id, l.block_id, l.subject_id, l.teacher_id
    FROM tmp_legacy_section_electives_conv l
    WHERE l.teacher_id IS NOT NULL
    ON CONFLICT DO NOTHING;
  END IF;
END $$;

-- 4) Drop legacy table (after backup + conversion)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_name = 'section_electives'
  ) THEN
    EXECUTE 'DROP TABLE section_electives';
  END IF;
END $$;

COMMIT;
