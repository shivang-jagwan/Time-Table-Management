begin;

-- Make the seeded Year 3 (CSE Sem 6) dataset solver-ready:
-- - Add section_time_windows for all sections in Year 3
-- - Select one elective per CORE section (since CORE has elective options)

do $$
declare
  v_year3_id uuid;
  v_program_id uuid;
  v_elective_subject_id uuid;
  v_section record;
  d int;
begin
  select id into v_year3_id from academic_years where year_number = 3;
  if v_year3_id is null then
    raise exception 'academic_years.year_number=3 not found';
  end if;

  select id into v_program_id from programs where code = 'CSE';
  if v_program_id is null then
    raise exception 'program CSE not found';
  end if;

  -- Pick a default elective for CORE sections.
  select id into v_elective_subject_id
  from subjects
  where program_id = v_program_id
    and academic_year_id = v_year3_id
    and semester = 6
    and code = 'TCS692'
  limit 1;

  if v_elective_subject_id is null then
    raise exception 'default elective subject TCS692 not found for CSE Year 3 Sem 6';
  end if;

  for v_section in
    select id, track
    from sections
    where program_id = v_program_id
      and academic_year_id = v_year3_id
      and semester = 6
  loop
    -- Add full-week window (all slots) for each day.
    for d in 0..5 loop
      insert into section_time_windows(section_id, day_of_week, start_slot_index, end_slot_index)
      values (v_section.id, d, 0, 5)
      on conflict (section_id, day_of_week, start_slot_index, end_slot_index) do nothing;
    end loop;

    -- CORE sections must have exactly one elective selection.
    if v_section.track = 'CORE' then
      insert into section_electives(section_id, subject_id)
      values (v_section.id, v_elective_subject_id)
      on conflict (section_id) do update set subject_id = excluded.subject_id;
    end if;
  end loop;
end $$;

commit;
