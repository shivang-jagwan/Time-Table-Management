begin;

-- Add missing tables referenced by ORM / solver: section_time_windows, section_breaks

create table if not exists section_time_windows (
  id uuid primary key default gen_random_uuid(),
  section_id uuid not null references sections(id) on delete cascade,
  day_of_week int not null,
  start_slot_index int not null,
  end_slot_index int not null,
  created_at timestamptz not null default now(),
  constraint ck_section_windows_day check (day_of_week >= 0 and day_of_week <= 5),
  constraint ck_section_windows_start check (start_slot_index >= 0),
  constraint ck_section_windows_end check (end_slot_index >= 0),
  constraint ck_section_windows_order check (end_slot_index >= start_slot_index)
);

create index if not exists idx_section_time_windows_section_day
  on section_time_windows(section_id, day_of_week);

create unique index if not exists ux_section_time_windows_unique
  on section_time_windows(section_id, day_of_week, start_slot_index, end_slot_index);

create table if not exists section_breaks (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references timetable_runs(id) on delete cascade,
  section_id uuid not null references sections(id) on delete cascade,
  day_of_week int not null,
  slot_id uuid not null references time_slots(id) on delete cascade,
  created_at timestamptz not null default now()
);

create index if not exists idx_section_breaks_run_section
  on section_breaks(run_id, section_id);

create index if not exists idx_section_breaks_slot
  on section_breaks(slot_id);

commit;
