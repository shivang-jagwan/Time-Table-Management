begin;

-- Expand teacher eligibility for Year 3 (CSE Sem 6) to satisfy strict capacity validation.
-- The validation sums max_per_week of eligible teachers per subject; with many sections,
-- single-teacher eligibility is insufficient.

do $$
declare
  v_year3_id uuid;
  v_program_id uuid;
begin
  select id into v_year3_id from academic_years where year_number = 3;
  if v_year3_id is null then
    raise exception 'academic_years.year_number=3 not found';
  end if;

  select id into v_program_id from programs where code = 'CSE';
  if v_program_id is null then
    raise exception 'program CSE not found';
  end if;
end $$;

with
ay as (select id as academic_year_id from academic_years where year_number = 3),
p as (select id as program_id from programs where code = 'CSE'),
subj as (
  select id as subject_id, code
  from subjects
  where program_id = (select program_id from p)
    and academic_year_id = (select academic_year_id from ay)
    and semester = 6
),
teach as (
  select id as teacher_id, full_name
  from teachers
),
seed(full_name, subject_code) as (
  values
    -- TCS611 Software Engineering: add capacity
    ('Ilearn Platform', 'TCS611'),
    ('Dr. Susheela Dahiya', 'TCS611'),
    ('Mr. Sushant Chamoli', 'TCS611'),
    ('Mr. Samir Rana', 'TCS611'),

    -- TCS692 LLMs/GenAI: add capacity
    ('Dr. Seema Gulati', 'TCS692'),
    ('Dr. Saumitra Chattopadhyay', 'TCS692'),
    ('Dr. Vikrant Sharma', 'TCS692'),
    ('Dr. Chandradeep Bhatt', 'TCS692')
)
insert into teacher_subjects (teacher_id, subject_id)
select teach.teacher_id, subj.subject_id
from seed
join teach on teach.full_name = seed.full_name
join subj on subj.code = seed.subject_code
on conflict (teacher_id, subject_id) do nothing;

commit;
