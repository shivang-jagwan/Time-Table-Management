begin;

-- Resolves program_id by programs.code = 'CSE'
-- Resolves subject_id by subjects.program_id + subjects.semester=6 and matches code ignoring spaces.
-- Raises a clear exception if any required subject code is missing.

do $$
declare
  v_program_id uuid;
begin
  select id into v_program_id from programs where code = 'CSE';
  if v_program_id is null then
    raise exception 'Program code CSE not found in programs table';
  end if;
end $$;

do $$
declare
  v_program_id uuid;
  missing text;
begin
  select id into v_program_id from programs where code = 'CSE';

  with required(code_key) as (
    values
      -- CORE base
      ('TCS601'), ('TCS611'), ('TCS614'), ('TCS693'), ('XCS601'), ('PESE600'),
      -- CORE electives (4 options)
      ('TCS692'), ('TCS651'), ('TCS619'), ('TCS695'),
      -- CYBER
      ('TCS679'), ('TCS696'),
      -- AI_DS
      ('TCS663'),
      -- AI_ML
      ('TCS666')
  ),
  existing as (
    select replace(upper(code), ' ', '') as code_key
    from subjects
    where program_id = v_program_id
      and semester = 6
  )
  select string_agg(r.code_key, ', ')
  into missing
  from required r
  left join existing e on e.code_key = r.code_key
  where e.code_key is null;

  if missing is not null then
    raise exception 'Missing subjects in DB for CSE sem 6: %', missing;
  end if;
end $$;

with
p as (
  select id as program_id from programs where code = 'CSE'
),
s as (
  select
    id as subject_id,
    program_id,
    semester,
    replace(upper(code), ' ', '') as code_key
  from subjects
  where program_id = (select program_id from p)
    and semester = 6
),
seed(track, code_key, is_elective) as (
  values
    -- CORE (base)
    ('CORE'::section_track, 'TCS601', false),
    ('CORE'::section_track, 'TCS611', false),
    ('CORE'::section_track, 'TCS614', false),
    ('CORE'::section_track, 'TCS693', false),
    ('CORE'::section_track, 'XCS601', false),
    ('CORE'::section_track, 'PESE600', false),

    -- CORE electives (4 options)
    ('CORE'::section_track, 'TCS692', true),
    ('CORE'::section_track, 'TCS651', true),
    ('CORE'::section_track, 'TCS619', true),
    ('CORE'::section_track, 'TCS695', true),

    -- CYBER
    ('CYBER'::section_track, 'TCS601', false),
    ('CYBER'::section_track, 'TCS611', false),
    ('CYBER'::section_track, 'TCS693', false),
    ('CYBER'::section_track, 'TCS679', false),
    ('CYBER'::section_track, 'TCS696', false),
    ('CYBER'::section_track, 'TCS695', false),
    ('CYBER'::section_track, 'XCS601', false),
    ('CYBER'::section_track, 'PESE600', false),

    -- AI_DS
    ('AI_DS'::section_track, 'TCS601', false),
    ('AI_DS'::section_track, 'TCS611', false),
    ('AI_DS'::section_track, 'TCS693', false),
    ('AI_DS'::section_track, 'TCS663', false),
    ('AI_DS'::section_track, 'TCS692', false),
    ('AI_DS'::section_track, 'XCS601', false),
    ('AI_DS'::section_track, 'PESE600', false),

    -- AI_ML
    ('AI_ML'::section_track, 'TCS601', false),
    ('AI_ML'::section_track, 'TCS611', false),
    ('AI_ML'::section_track, 'TCS693', false),
    ('AI_ML'::section_track, 'TCS666', false),
    ('AI_ML'::section_track, 'TCS692', false),
    ('AI_ML'::section_track, 'XCS601', false),
    ('AI_ML'::section_track, 'PESE600', false)
)
insert into track_subjects (
  program_id, semester, track, subject_id, is_elective, sessions_override
)
select
  (select program_id from p) as program_id,
  6 as semester,
  seed.track,
  s.subject_id,
  seed.is_elective,
  null::int as sessions_override
from seed
join s on s.code_key = seed.code_key
on conflict (program_id, semester, track, subject_id) do nothing;

commit;
