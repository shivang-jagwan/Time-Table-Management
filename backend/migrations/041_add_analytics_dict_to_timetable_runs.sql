-- Migration: Add analytics_dict JSONB column to timetable_runs table
-- Purpose: Store solver analytics (penalties, violations, metrics) for observability
-- Date: April 5, 2026

ALTER TABLE timetable_runs
ADD COLUMN analytics_dict JSONB NULL;

-- Optional: Add index for faster queries if needed
-- CREATE INDEX idx_timetable_runs_analytics_dict ON timetable_runs USING GIN(analytics_dict);

COMMIT;
