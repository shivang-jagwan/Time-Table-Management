-- Add structured details payload to conflicts for richer diagnostics.
-- Note: project uses table `timetable_conflicts` (not `solver_conflicts`).

ALTER TABLE timetable_conflicts
ADD COLUMN IF NOT EXISTS details JSONB NULL;

-- Backfill: preserve existing metadata payloads for old conflicts.
UPDATE timetable_conflicts
SET details = metadata
WHERE details IS NULL;
