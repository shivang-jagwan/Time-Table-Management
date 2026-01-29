# Migrations

Put Supabase SQL scripts or migration notes here.

Run a migration SQL file (uses backend/.env DATABASE_URL):

`python migrations/run_sql.py migrations/005_add_section_subjects.sql`

## 2026-01: Academic-year solver upgrade

The solver schedules timetables by academic year (and optionally program-wide across all years).

DB change:

- `timetable_runs.academic_year_id` is now nullable (runs can span multiple years).
- Year identity is preserved per entry in `timetable_entries.academic_year_id`.

Apply:

`python migrations/run_sql.py migrations/017_make_timetable_runs_academic_year_nullable.sql`

## 2026-01: Remove teacher email/phone

Teacher `email` and `phone` are removed from the API/UI. If you want to physically drop the unused DB columns:

`python migrations/run_sql.py migrations/020_drop_teacher_email_phone.sql`
