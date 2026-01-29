begin;

-- =========================================================
-- Seed: Teacher → Subject eligibility (CSE Semester 6)
-- Resolves teachers by teachers.full_name
-- Resolves subjects by subjects.code (ignoring spaces), program=CSE, semester=6
-- =========================================================

-- Guard: ensure program exists
do $$
declare
	v_program_id uuid;
begin
	select id into v_program_id from programs where code = 'CSE';
	if v_program_id is null then
		raise exception 'Program code CSE not found in programs table';
	end if;
end $$;

with
p as (
	select id as program_id from programs where code = 'CSE'
),
subj as (
	select id as subject_id, replace(upper(code), ' ', '') as code_key
	from subjects
	where program_id = (select program_id from p)
		and semester = 6
),
teach as (
	select id as teacher_id, full_name
	from teachers
),
seed(full_name, code_key) as (
	values
		-- Compiler Design (TCS601 + PCS601)
		('Dr. Chandradeep Bhatt', 'TCS601'),
		('Dr. Chandradeep Bhatt', 'PCS601'),
		('Ms. Himadri Vaidya', 'TCS601'),
		('Ms. Himadri Vaidya', 'PCS601'),
		('Mr. Mukesh Kumar', 'TCS601'),
		('Mr. Mukesh Kumar', 'PCS601'),
		('Mr. Tushar Sharma', 'TCS601'),
		('Mr. Tushar Sharma', 'PCS601'),
		('Ms. Manika Manwal', 'TCS601'),
		('Ms. Manika Manwal', 'PCS601'),
		('Ms. Sonal Malhotra', 'TCS601'),
		('Ms. Sonal Malhotra', 'PCS601'),
		('Ms. Pallavi Tiwari', 'PCS601'),
		('Ms. Manisha Aeri', 'PCS601'),
		('Mr. Nishant Bhandari', 'PCS601'),

		-- Software Engineering (TCS611)
		('Ilearn Platform', 'TCS611'),

		-- Computer Networks – II (TCS614 + PCS614)
		('Dr. Vikrant Sharma', 'TCS614'),
		('Dr. Vikrant Sharma', 'PCS614'),
		('Dr. Ashok Sahoo', 'TCS614'),
		('Dr. Ashok Sahoo', 'PCS614'),
		('Ms. Preeti Chaudhary', 'TCS614'),
		('Ms. Preeti Chaudhary', 'PCS614'),
		('Mr. Purushottam Das', 'TCS614'),
		('Mr. Purushottam Das', 'PCS614'),
		('Ms. Richa Gupta', 'TCS614'),
		('Ms. Richa Gupta', 'PCS614'),
		('Ms. Lisa Gopal', 'PCS614'),

		-- Full Stack Web Development (TCS693 + PCS693)
		('Mr. Sushant Chamoli', 'TCS693'),
		('Mr. Sushant Chamoli', 'PCS693'),
		('Mr. Samir Rana', 'TCS693'),
		('Dr. Susheela Dahiya', 'TCS693'),
		('Dr. Susheela Dahiya', 'PCS693'),
		('Ms. Shraddha Kaparwan', 'TCS693'),
		('Ms. Shraddha Kaparwan', 'PCS693'),
		('Mr. Saksham Mittal', 'TCS693'),
		('Mr. Saksham Mittal', 'PCS693'),
		('Mr. Daksh Rawat', 'PCS693'),
		('Mr. Prateek Kumar', 'PCS693'),
		('Ms. Tashi Negi', 'PCS693'),

		-- Career Skills (XCS601)
		('Dr. P.A. Anand', 'XCS601'),
		('Mr. Ankur Sharma', 'XCS601'),
		('Mr. Saurabh Fulara', 'XCS601'),
		('Mr. Suhail Vij', 'XCS601'),
		('Mr. Vishal Chhabra', 'XCS601'),

		-- Electives and specialization subjects
		('Dr. Seema Gulati', 'TCS692'),
		('Ms. Stuti Bhatt', 'TCS651'),
		('Dr. Saumitra Chattopadhyay', 'TCS619'),
		('Dr. Saumitra Chattopadhyay', 'TCS695'),
		('Dr. Saumitra Chattopadhyay', 'TCS696'),

		-- Cyber Security specialization
		('Ms. Amrita Tiwari', 'TCS679'),
		('Ms. Amrita Tiwari', 'PCS679'),

		-- AI / DS specialization
		('Mr. Nitin Thapliyal', 'TCS663'),
		('Mr. Nitin Thapliyal', 'PCS663'),

		-- AI / ML specialization
		('Ms. Neha Pokhriyal', 'TCS666'),
		('Ms. Neha Pokhriyal', 'PCS666'),

		-- PESE600
		('Dr. Animesh Sharma', 'PESE600'),
		('Ms. Neelam Kathait', 'PESE600'),
		('Mr. Anshuman Sharma', 'PESE600'),
		('Mr. Rana Pratap Singh', 'PESE600'),
		('Ms. Nupur Dube', 'PESE600')
),
missing_teachers as (
	select distinct seed.full_name
	from seed
	left join teach on teach.full_name = seed.full_name
	where teach.teacher_id is null
),
missing_subjects as (
	select distinct seed.code_key
	from seed
	left join subj on subj.code_key = seed.code_key
	where subj.subject_id is null
)
select 1
where not exists (select 1 from missing_teachers)
	and not exists (select 1 from missing_subjects);

-- Raise explicit errors if anything is missing (helps diagnose seeding order problems)
do $$
declare
	mt text;
	ms text;
begin
	select string_agg(full_name, ', ') into mt from (
		with seed(full_name) as (
			values
				('Dr. Chandradeep Bhatt'),('Ms. Himadri Vaidya'),('Mr. Mukesh Kumar'),('Mr. Tushar Sharma'),('Ms. Manika Manwal'),('Ms. Sonal Malhotra'),('Ms. Pallavi Tiwari'),('Ms. Manisha Aeri'),('Mr. Nishant Bhandari'),
				('Ilearn Platform'),
				('Dr. Vikrant Sharma'),('Dr. Ashok Sahoo'),('Ms. Preeti Chaudhary'),('Mr. Purushottam Das'),('Ms. Richa Gupta'),('Ms. Lisa Gopal'),
				('Mr. Sushant Chamoli'),('Mr. Samir Rana'),('Dr. Susheela Dahiya'),('Ms. Shraddha Kaparwan'),('Mr. Saksham Mittal'),('Mr. Daksh Rawat'),('Mr. Prateek Kumar'),('Ms. Tashi Negi'),
				('Dr. P.A. Anand'),('Mr. Ankur Sharma'),('Mr. Saurabh Fulara'),('Mr. Suhail Vij'),('Mr. Vishal Chhabra'),
				('Dr. Seema Gulati'),('Ms. Stuti Bhatt'),('Dr. Saumitra Chattopadhyay'),
				('Ms. Amrita Tiwari'),('Mr. Nitin Thapliyal'),('Ms. Neha Pokhriyal'),
				('Dr. Animesh Sharma'),('Ms. Neelam Kathait'),('Mr. Anshuman Sharma'),('Mr. Rana Pratap Singh'),('Ms. Nupur Dube')
		)
		select seed.full_name
		from seed
		left join teachers t on t.full_name = seed.full_name
		where t.id is null
	) x;

	if mt is not null then
		raise exception 'Missing teachers (run 003_seed_cse_sem6_master_data.sql first): %', mt;
	end if;

	select string_agg(code_key, ', ') into ms from (
		with p as (select id as program_id from programs where code='CSE'),
		subj as (
			select replace(upper(code), ' ', '') as code_key
			from subjects
			where program_id=(select program_id from p) and semester=6
		),
		seed(code_key) as (
			values
				('TCS601'),('PCS601'),('TCS611'),('TCS614'),('PCS614'),('TCS693'),('PCS693'),('XCS601'),('TCS692'),('TCS651'),('TCS619'),('TCS695'),('TCS696'),('TCS679'),('PCS679'),('TCS663'),('PCS663'),('TCS666'),('PCS666'),('PESE600')
		)
		select seed.code_key
		from seed
		left join subj on subj.code_key = seed.code_key
		where subj.code_key is null
	) y;

	if ms is not null then
		raise exception 'Missing subjects for CSE sem 6 (run 003_seed_cse_sem6_master_data.sql first): %', ms;
	end if;
end $$;

-- Insert eligibility rows
with
p as (
	select id as program_id from programs where code = 'CSE'
),
subj as (
	select id as subject_id, replace(upper(code), ' ', '') as code_key
	from subjects
	where program_id = (select program_id from p)
		and semester = 6
),
teach as (
	select id as teacher_id, full_name
	from teachers
),
seed(full_name, code_key) as (
	values
		('Dr. Chandradeep Bhatt', 'TCS601'),('Dr. Chandradeep Bhatt', 'PCS601'),
		('Ms. Himadri Vaidya', 'TCS601'),('Ms. Himadri Vaidya', 'PCS601'),
		('Mr. Mukesh Kumar', 'TCS601'),('Mr. Mukesh Kumar', 'PCS601'),
		('Mr. Tushar Sharma', 'TCS601'),('Mr. Tushar Sharma', 'PCS601'),
		('Ms. Manika Manwal', 'TCS601'),('Ms. Manika Manwal', 'PCS601'),
		('Ms. Sonal Malhotra', 'TCS601'),('Ms. Sonal Malhotra', 'PCS601'),
		('Ms. Pallavi Tiwari', 'PCS601'),
		('Ms. Manisha Aeri', 'PCS601'),
		('Mr. Nishant Bhandari', 'PCS601'),

		('Ilearn Platform', 'TCS611'),

		('Dr. Vikrant Sharma', 'TCS614'),('Dr. Vikrant Sharma', 'PCS614'),
		('Dr. Ashok Sahoo', 'TCS614'),('Dr. Ashok Sahoo', 'PCS614'),
		('Ms. Preeti Chaudhary', 'TCS614'),('Ms. Preeti Chaudhary', 'PCS614'),
		('Mr. Purushottam Das', 'TCS614'),('Mr. Purushottam Das', 'PCS614'),
		('Ms. Richa Gupta', 'TCS614'),('Ms. Richa Gupta', 'PCS614'),
		('Ms. Lisa Gopal', 'PCS614'),

		('Mr. Sushant Chamoli', 'TCS693'),('Mr. Sushant Chamoli', 'PCS693'),
		('Mr. Samir Rana', 'TCS693'),
		('Dr. Susheela Dahiya', 'TCS693'),('Dr. Susheela Dahiya', 'PCS693'),
		('Ms. Shraddha Kaparwan', 'TCS693'),('Ms. Shraddha Kaparwan', 'PCS693'),
		('Mr. Saksham Mittal', 'TCS693'),('Mr. Saksham Mittal', 'PCS693'),
		('Mr. Daksh Rawat', 'PCS693'),
		('Mr. Prateek Kumar', 'PCS693'),
		('Ms. Tashi Negi', 'PCS693'),

		('Dr. P.A. Anand', 'XCS601'),
		('Mr. Ankur Sharma', 'XCS601'),
		('Mr. Saurabh Fulara', 'XCS601'),
		('Mr. Suhail Vij', 'XCS601'),
		('Mr. Vishal Chhabra', 'XCS601'),

		('Dr. Seema Gulati', 'TCS692'),
		('Ms. Stuti Bhatt', 'TCS651'),
		('Dr. Saumitra Chattopadhyay', 'TCS619'),
		('Dr. Saumitra Chattopadhyay', 'TCS695'),
		('Dr. Saumitra Chattopadhyay', 'TCS696'),

		('Ms. Amrita Tiwari', 'TCS679'),('Ms. Amrita Tiwari', 'PCS679'),

		('Mr. Nitin Thapliyal', 'TCS663'),('Mr. Nitin Thapliyal', 'PCS663'),

		('Ms. Neha Pokhriyal', 'TCS666'),('Ms. Neha Pokhriyal', 'PCS666'),

		('Dr. Animesh Sharma', 'PESE600'),
		('Ms. Neelam Kathait', 'PESE600'),
		('Mr. Anshuman Sharma', 'PESE600'),
		('Mr. Rana Pratap Singh', 'PESE600'),
		('Ms. Nupur Dube', 'PESE600')
)
insert into teacher_subjects (teacher_id, subject_id)
select teach.teacher_id, subj.subject_id
from seed
join teach on teach.full_name = seed.full_name
join subj on subj.code_key = seed.code_key
on conflict (teacher_id, subject_id) do nothing;

commit;
