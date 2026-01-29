begin;

-- section_subjects
-- Explicit Section ↔ Subject mapping. If a section has any rows here, the solver will use ONLY these subjects.

create table if not exists section_subjects (
  id uuid primary key default gen_random_uuid(),
  section_id uuid not null references sections(id) on delete cascade,
  subject_id uuid not null references subjects(id) on delete cascade,
  created_at timestamptz not null default now(),
  constraint uq_section_subjects unique (section_id, subject_id)
);

create index if not exists idx_section_subjects_section_id
  on section_subjects(section_id);

create index if not exists idx_section_subjects_subject_id
  on section_subjects(subject_id);

commit;
