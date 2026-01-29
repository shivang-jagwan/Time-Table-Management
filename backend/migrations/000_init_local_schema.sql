-- Fresh local PostgreSQL schema for University Timetable System
-- Focus: multi-year scheduling with cross-year teacher clash prevention.

BEGIN;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================
-- ENUMS
-- =========================
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('ADMIN', 'USER');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE subject_type AS ENUM ('THEORY', 'LAB');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE room_type AS ENUM ('CLASSROOM', 'LT', 'LAB');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE section_track AS ENUM ('CORE', 'CYBER', 'AI_DS', 'AI_ML');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE run_status AS ENUM ('CREATED', 'VALIDATION_FAILED', 'INFEASIBLE', 'FEASIBLE', 'OPTIMAL', 'ERROR');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE conflict_severity AS ENUM ('INFO', 'WARN', 'ERROR');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =========================
-- PHASE 1 — AUTH (DEV)
-- =========================
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    role user_role NOT NULL DEFAULT 'USER',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_users_role ON users(role);

-- =========================
-- SUPPORTING MASTER DATA
-- =========================
CREATE TABLE IF NOT EXISTS programs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rooms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    room_type room_type NOT NULL,
    capacity integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_rooms_capacity CHECK (capacity >= 0)
);

CREATE TABLE IF NOT EXISTS time_slots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    day_of_week integer NOT NULL,
    slot_index integer NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_time_slots_day CHECK (day_of_week >= 0 AND day_of_week <= 5),
    CONSTRAINT ck_time_slots_slot_index CHECK (slot_index >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_time_slots_day_slot ON time_slots(day_of_week, slot_index);

-- =========================
-- PHASE 2 — ACADEMIC STRUCTURE
-- =========================
CREATE TABLE IF NOT EXISTS academic_years (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    year_number integer NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_academic_years_year_number CHECK (year_number >= 1 AND year_number <= 4),
    CONSTRAINT ux_academic_years_year_number UNIQUE (year_number)
);

CREATE TABLE IF NOT EXISTS sections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE RESTRICT,
    academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    code text NOT NULL,
    name text NOT NULL,
    track section_track NOT NULL DEFAULT 'CORE',
    strength integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_sections_strength CHECK (strength >= 0)
);

CREATE INDEX IF NOT EXISTS ix_sections_program_year ON sections(program_id, academic_year_id);
CREATE INDEX IF NOT EXISTS ix_sections_year_active ON sections(academic_year_id, is_active);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sections_year_code ON sections(academic_year_id, code);

-- =========================
-- PHASE 3 — SUBJECTS
-- =========================
CREATE TABLE IF NOT EXISTS subjects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE RESTRICT,
    academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    code text NOT NULL,
    name text NOT NULL,
    subject_type subject_type NOT NULL,
    sessions_per_week integer NOT NULL,
    max_per_day integer NOT NULL DEFAULT 1,
    lab_block_size_slots integer NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_subjects_sessions_per_week CHECK (sessions_per_week >= 0),
    CONSTRAINT ck_subjects_max_per_day CHECK (max_per_day >= 0),
    CONSTRAINT ck_subjects_lab_block_size CHECK (lab_block_size_slots >= 1)
);

CREATE INDEX IF NOT EXISTS ix_subjects_program_year ON subjects(program_id, academic_year_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_subjects_year_code ON subjects(academic_year_id, code);

-- =========================
-- PHASE 4 — TEACHERS (GLOBAL)
-- =========================
CREATE TABLE IF NOT EXISTS teachers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    full_name text NOT NULL,
    email text NULL,
    phone text NULL,
    weekly_off_day integer NULL,
    max_per_day integer NOT NULL DEFAULT 4,
    max_per_week integer NOT NULL DEFAULT 20,
    max_continuous integer NOT NULL DEFAULT 3,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_teachers_weekly_off_day_range CHECK (weekly_off_day IS NULL OR (weekly_off_day >= 0 AND weekly_off_day <= 5)),
    CONSTRAINT ck_teachers_max_per_day CHECK (max_per_day >= 0),
    CONSTRAINT ck_teachers_max_per_week CHECK (max_per_week >= 0),
    CONSTRAINT ck_teachers_max_continuous CHECK (max_continuous >= 1)
);

-- Optional but practically required: which teachers can teach which subjects
CREATE TABLE IF NOT EXISTS teacher_subjects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE CASCADE,
    subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ux_teacher_subject UNIQUE (teacher_id, subject_id)
);

CREATE INDEX IF NOT EXISTS ix_teacher_subjects_subject ON teacher_subjects(subject_id);

-- =========================
-- PHASE 5 — SECTION SUBJECT MAPPING
-- =========================
CREATE TABLE IF NOT EXISTS section_subjects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ux_section_subject UNIQUE (section_id, subject_id)
);

CREATE INDEX IF NOT EXISTS ix_section_subjects_subject ON section_subjects(subject_id);

-- =========================
-- PHASE 6 — TIMETABLE RUNS
-- =========================
CREATE TABLE IF NOT EXISTS timetable_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    status run_status NOT NULL DEFAULT 'CREATED',
    seed integer NULL,
    solver_version text NULL,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes text NULL
);

CREATE INDEX IF NOT EXISTS ix_runs_year_created ON timetable_runs(academic_year_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_year_status ON timetable_runs(academic_year_id, status);

-- =========================
-- PHASE 7 — TIMETABLE ENTRIES
-- =========================
CREATE TABLE IF NOT EXISTS timetable_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES timetable_runs(id) ON DELETE CASCADE,
    academic_year_id uuid NOT NULL REFERENCES academic_years(id) ON DELETE RESTRICT,
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
    teacher_id uuid NOT NULL REFERENCES teachers(id) ON DELETE RESTRICT,
    room_id uuid NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    slot_id uuid NOT NULL REFERENCES time_slots(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),

    combined_class_id uuid NULL,

    -- Uniqueness rules (as requested)
    CONSTRAINT ux_entries_run_section_slot UNIQUE (run_id, section_id, slot_id),
    CONSTRAINT ux_entries_run_room_slot UNIQUE (run_id, room_id, slot_id)

    -- NOTE: teacher uniqueness is intentionally NOT enforced at DB level.
);

-- Fast filtering for per-year UI and for cross-year fixed constraints
CREATE INDEX IF NOT EXISTS ix_entries_year ON timetable_entries(academic_year_id);
CREATE INDEX IF NOT EXISTS ix_entries_year_slot ON timetable_entries(academic_year_id, slot_id);
CREATE INDEX IF NOT EXISTS ix_entries_teacher_slot ON timetable_entries(teacher_id, slot_id);
CREATE INDEX IF NOT EXISTS ix_entries_run ON timetable_entries(run_id);

-- Conflicts / validation output (keeps existing behavior possible)
CREATE TABLE IF NOT EXISTS timetable_conflicts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES timetable_runs(id) ON DELETE CASCADE,
    severity conflict_severity NOT NULL DEFAULT 'ERROR',
    conflict_type text NOT NULL,
    message text NOT NULL,

    section_id uuid NULL REFERENCES sections(id) ON DELETE SET NULL,
    teacher_id uuid NULL REFERENCES teachers(id) ON DELETE SET NULL,
    subject_id uuid NULL REFERENCES subjects(id) ON DELETE SET NULL,
    room_id uuid NULL REFERENCES rooms(id) ON DELETE SET NULL,
    slot_id uuid NULL REFERENCES time_slots(id) ON DELETE SET NULL,

    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_conflicts_run_severity ON timetable_conflicts(run_id, severity);

COMMIT;
