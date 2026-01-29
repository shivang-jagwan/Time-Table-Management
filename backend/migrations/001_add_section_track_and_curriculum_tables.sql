begin;

-- 1) Enum: section_track
do $$
begin
  if not exists (select 1 from pg_type where typname = 'section_track') then
    create type section_track as enum ('CORE', 'CYBER', 'AI_DS', 'AI_ML');
  end if;
end $$;

-- 2) sections.track
alter table sections
  add column if not exists track section_track not null default 'CORE';

-- 3) track_subjects
create table if not exists track_subjects (
  id uuid primary key default gen_random_uuid(),
  program_id uuid not null references programs(id) on delete cascade,
  semester smallint not null,
  track section_track not null,
  subject_id uuid not null references subjects(id) on delete cascade,
  is_elective boolean not null default false,
  sessions_override int null,
  created_at timestamptz not null default now(),
  constraint uq_track_subjects unique (program_id, semester, track, subject_id),
  constraint ck_track_subjects_semester check (semester >= 1 and semester <= 12),
  constraint ck_track_subjects_sessions_override check (sessions_override is null or sessions_override >= 0)
);

-- 4) section_electives
create table if not exists section_electives (
  id uuid primary key default gen_random_uuid(),
  section_id uuid not null references sections(id) on delete cascade,
  subject_id uuid not null references subjects(id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint uq_section_electives_section unique (section_id)
);

-- 5) Indexes
create index if not exists idx_sections_track on sections(track);

create index if not exists idx_track_subjects_lookup
  on track_subjects(program_id, semester, track);

create index if not exists idx_track_subjects_subject
  on track_subjects(subject_id);

create index if not exists idx_section_electives_subject
  on section_electives(subject_id);

commit;
