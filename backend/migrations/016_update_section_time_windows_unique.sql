BEGIN;

-- =========================================================
-- Section Working Time Windows
--
-- Align uniqueness with the "one window per section per day" rule:
--   UNIQUE(section_id, day_of_week)
--
-- Older migration allowed multiple rows per day (unique included start/end).
-- We dedupe conservatively (keep most recent) and then add the correct unique index.
-- =========================================================

-- 1) Dedupe any accidental duplicates per (section_id, day_of_week)
WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY section_id, day_of_week
      ORDER BY created_at DESC, id DESC
    ) AS rn
  FROM section_time_windows
)
DELETE FROM section_time_windows stw
USING ranked r
WHERE stw.id = r.id
  AND r.rn > 1;

-- 2) Drop old unique index if present
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname = 'ux_section_time_windows_unique'
  ) THEN
    EXECUTE 'DROP INDEX ux_section_time_windows_unique';
  END IF;
END $$;

-- 3) Enforce the correct uniqueness
CREATE UNIQUE INDEX IF NOT EXISTS ux_section_time_windows_section_day
  ON section_time_windows(section_id, day_of_week);

COMMIT;
