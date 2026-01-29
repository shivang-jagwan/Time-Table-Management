begin;

-- =========================================================
-- Seed: CSE Semester 6 master data
-- Inserts ONLY (no table creation, no schema changes).
-- Does NOT seed: time_slots, combined_classes, timetable_runs, timetable_entries, section_electives.
-- =========================================================

-- ---------- Program ----------
insert into programs (code, name)
values ('CSE', 'Computer Science and Engineering')
on conflict (code) do update set name = excluded.name;

-- ---------- Sections (Semester 6) ----------
with p as (
  select id as program_id from programs where code = 'CSE'
),
seed(code, name, track) as (
  values
    -- CORE
    ('A1', 'CSE Sem 6 A1', 'CORE'::section_track),
    ('A2', 'CSE Sem 6 A2', 'CORE'::section_track),
    ('B1', 'CSE Sem 6 B1', 'CORE'::section_track),
    ('B2', 'CSE Sem 6 B2', 'CORE'::section_track),
    ('C1', 'CSE Sem 6 C1', 'CORE'::section_track),
    ('C2', 'CSE Sem 6 C2', 'CORE'::section_track),
    ('D1', 'CSE Sem 6 D1', 'CORE'::section_track),
    ('D2', 'CSE Sem 6 D2', 'CORE'::section_track),
    ('E1', 'CSE Sem 6 E1', 'CORE'::section_track),
    ('E2', 'CSE Sem 6 E2', 'CORE'::section_track),
    ('F1', 'CSE Sem 6 F1', 'CORE'::section_track),
    ('F2', 'CSE Sem 6 F2', 'CORE'::section_track),
    ('G1', 'CSE Sem 6 G1', 'CORE'::section_track),
    ('G2', 'CSE Sem 6 G2', 'CORE'::section_track),
    ('H1', 'CSE Sem 6 H1', 'CORE'::section_track),
    ('H2', 'CSE Sem 6 H2', 'CORE'::section_track),
    ('I1', 'CSE Sem 6 I1', 'CORE'::section_track),

    -- CYBER
    ('CS-1', 'CSE Sem 6 CS-1 (CYBER)', 'CYBER'::section_track),

    -- AI_DS
    ('DS-1', 'CSE Sem 6 DS-1 (AI_DS)', 'AI_DS'::section_track),
    ('DS-2', 'CSE Sem 6 DS-2 (AI_DS)', 'AI_DS'::section_track),

    -- AI_ML
    ('ML-1', 'CSE Sem 6 ML-1 (AI_ML)', 'AI_ML'::section_track),
    ('ML-2', 'CSE Sem 6 ML-2 (AI_ML)', 'AI_ML'::section_track)
)
insert into sections (program_id, semester, code, name, strength, track, is_active)
select p.program_id, 6, seed.code, seed.name, 0, seed.track, true
from seed
cross join p
on conflict (program_id, semester, code)
do update set
  name = excluded.name,
  track = excluded.track,
  is_active = excluded.is_active;

-- ---------- Subjects (Semester 6) ----------
-- Theory subjects: subject_type=THEORY, lab_block_size_slots must be 1.
-- Lab subjects: subject_type=LAB, sessions_per_week=1, lab_block_size_slots=2.
with p as (
  select id as program_id from programs where code = 'CSE'
),
seed(code, name, subject_type, sessions_per_week, max_per_day, lab_block_size_slots) as (
  values
    -- THEORY
    ('TCS601', 'Compiler Design', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS611', 'Software Engineering', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS614', 'Computer Networks – II', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS693', 'Full Stack Web Development', 'THEORY'::subject_type, 3, 1, 1),
    ('XCS601', 'Career Skills', 'THEORY'::subject_type, 2, 1, 1),
    ('PESE600', 'Employability Skill Enhancement', 'THEORY'::subject_type, 1, 1, 1),

    -- CORE electives (THEORY, 3/week)
    ('TCS692', 'Large Language Models and Generative AI', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS651', 'DevOps on Cloud', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS619', 'Network and System Security', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS695', 'Security Audit and Compliance – II', 'THEORY'::subject_type, 3, 1, 1),

    -- CYBER specialization
    ('TCS679', 'Network and System Security', 'THEORY'::subject_type, 3, 1, 1),
    ('TCS696', 'Database Security, Identity & Access Management', 'THEORY'::subject_type, 3, 1, 1),

    -- AI_DS specialization
    ('TCS663', 'Big Data Analytics: Tools and Techniques', 'THEORY'::subject_type, 3, 1, 1),

    -- AI_ML specialization
    ('TCS666', 'Transformer Models and Applications', 'THEORY'::subject_type, 3, 1, 1),

    -- LABS
    ('PCS601', 'Compiler Design Lab', 'LAB'::subject_type, 1, 1, 2),
    ('PCS614', 'Computer Networks – II Lab', 'LAB'::subject_type, 1, 1, 2),
    ('PCS693', 'Web Development Lab', 'LAB'::subject_type, 1, 1, 2),
    ('PCS679', 'Network & System Security Lab', 'LAB'::subject_type, 1, 1, 2),
    ('PCS663', 'Data Science Lab-II', 'LAB'::subject_type, 1, 1, 2),
    ('PCS666', 'Transformer Models Lab', 'LAB'::subject_type, 1, 1, 2)
)
insert into subjects (program_id, semester, code, name, subject_type, sessions_per_week, max_per_day, lab_block_size_slots, is_active)
select p.program_id, 6, seed.code, seed.name, seed.subject_type, seed.sessions_per_week, seed.max_per_day, seed.lab_block_size_slots, true
from seed
cross join p
on conflict (program_id, semester, code)
do update set
  name = excluded.name,
  subject_type = excluded.subject_type,
  sessions_per_week = excluded.sessions_per_week,
  max_per_day = excluded.max_per_day,
  lab_block_size_slots = excluded.lab_block_size_slots,
  is_active = excluded.is_active;

-- ---------- Teachers ----------
-- All teachers inserted with: max_per_day=5, max_per_week=25, max_continuous=3, weekly_off_day=NULL
with seed(full_name, ord) as (
  values
    ('Dr. Chandradeep Bhatt', 1),
    ('Dr. Vikrant Sharma', 2),
    ('Dr. Seema Gulati', 3),
    ('Dr. Saumitra Chattopadhyay', 4),
    ('Dr. Ashok Sahoo', 5),
    ('Dr. Animesh Sharma', 6),
    ('Dr. Susheela Dahiya', 7),
    ('Ms. Himadri Vaidya', 8),
    ('Ms. Stuti Bhatt', 9),
    ('Ms. Preeti Chaudhary', 10),
    ('Ms. Manika Manwal', 11),
    ('Ms. Sonal Malhotra', 12),
    ('Ms. Richa Gupta', 13),
    ('Ms. Manisha Aeri', 14),
    ('Ms. Neha Pokhriyal', 15),
    ('Ms. Shraddha Kaparwan', 16),
    ('Ms. Amrita Tiwari', 17),
    ('Ms. Pallavi Tiwari', 18),
    ('Ms. Lisa Gopal', 19),
    ('Ms. Tashi Negi', 20),
    ('Ms. Nupur Dube', 21),
    ('Mr. Mukesh Kumar', 22),
    ('Mr. Sushant Chamoli', 23),
    ('Mr. Samir Rana', 24),
    ('Mr. Purushottam Das', 25),
    ('Mr. Tushar Sharma', 26),
    ('Mr. Saksham Mittal', 27),
    ('Mr. Daksh Rawat', 28),
    ('Mr. Nishant Bhandari', 29),
    ('Mr. Prateek Kumar', 30),
    ('Mr. Nitin Thapliyal', 31),
    ('Mr. Anshuman Sharma', 32),
    ('Mr. Rana Pratap Singh', 33),
    ('Mr. Suhail Vij', 34),
    ('Mr. Vishal Chhabra', 35),
    ('Mr. Ankur Sharma', 36),
    ('Mr. Saurabh Fulara', 37),
    ('Ilearn Platform', 38),
    ('Dr. P.A. Anand', 39),
    ('Ms. Neelam Kathait', 40)
)
insert into teachers (code, full_name, weekly_off_day, max_per_day, max_per_week, max_continuous, is_active)
select
  ('TCH' || lpad(seed.ord::text, 3, '0')) as code,
  seed.full_name,
  null::smallint as weekly_off_day,
  5 as max_per_day,
  25 as max_per_week,
  3 as max_continuous,
  true as is_active
from seed
on conflict (code)
do update set
  full_name = excluded.full_name,
  weekly_off_day = excluded.weekly_off_day,
  max_per_day = excluded.max_per_day,
  max_per_week = excluded.max_per_week,
  max_continuous = excluded.max_continuous,
  is_active = excluded.is_active;

-- ---------- Rooms ----------
-- Insert all rooms; solver will later filter by floors 1–3 per policy.
with seed(code, name, room_type) as (
  values
    -- CLASSROOMS
    ('CR101','CR101', 'CLASSROOM'::room_type),('CR102','CR102','CLASSROOM'::room_type),('CR103','CR103','CLASSROOM'::room_type),('CR104','CR104','CLASSROOM'::room_type),('CR105','CR105','CLASSROOM'::room_type),('CR106','CR106','CLASSROOM'::room_type),
    ('CR201','CR201', 'CLASSROOM'::room_type),('CR202','CR202','CLASSROOM'::room_type),('CR203','CR203','CLASSROOM'::room_type),('CR204','CR204','CLASSROOM'::room_type),('CR205','CR205','CLASSROOM'::room_type),('CR206','CR206','CLASSROOM'::room_type),
    ('CR301','CR301', 'CLASSROOM'::room_type),('CR302','CR302','CLASSROOM'::room_type),('CR303','CR303','CLASSROOM'::room_type),('CR304','CR304','CLASSROOM'::room_type),('CR305','CR305','CLASSROOM'::room_type),('CR306','CR306','CLASSROOM'::room_type),
    ('CR401','CR401', 'CLASSROOM'::room_type),('CR402','CR402','CLASSROOM'::room_type),('CR403','CR403','CLASSROOM'::room_type),('CR404','CR404','CLASSROOM'::room_type),('CR405','CR405','CLASSROOM'::room_type),('CR406','CR406','CLASSROOM'::room_type),
    ('CR501','CR501', 'CLASSROOM'::room_type),('CR502','CR502','CLASSROOM'::room_type),('CR503','CR503','CLASSROOM'::room_type),('CR504','CR504','CLASSROOM'::room_type),('CR505','CR505','CLASSROOM'::room_type),('CR506','CR506','CLASSROOM'::room_type),
    ('CR601','CR601', 'CLASSROOM'::room_type),('CR602','CR602','CLASSROOM'::room_type),('CR603','CR603','CLASSROOM'::room_type),('CR604','CR604','CLASSROOM'::room_type),('CR605','CR605','CLASSROOM'::room_type),('CR606','CR606','CLASSROOM'::room_type),

    -- LECTURE THEATRES
    ('LT101','LT101', 'LT'::room_type),('LT102','LT102','LT'::room_type),
    ('LT201','LT201', 'LT'::room_type),('LT202','LT202','LT'::room_type),
    ('LT301','LT301', 'LT'::room_type),('LT302','LT302','LT'::room_type),
    ('LT401','LT401', 'LT'::room_type),('LT402','LT402','LT'::room_type),
    ('LT501','LT501', 'LT'::room_type),('LT502','LT502','LT'::room_type),
    ('LT601','LT601', 'LT'::room_type),('LT602','LT602','LT'::room_type),

    -- LABS
    ('Lab1','Lab1','LAB'::room_type),('Lab2','Lab2','LAB'::room_type),('Lab3','Lab3','LAB'::room_type),('Lab4','Lab4','LAB'::room_type),('Lab5','Lab5','LAB'::room_type),
    ('Lab6','Lab6','LAB'::room_type),('Lab7','Lab7','LAB'::room_type),('Lab8','Lab8','LAB'::room_type),('Lab9','Lab9','LAB'::room_type),('Lab10','Lab10','LAB'::room_type),
    ('TCL1','TCL1','LAB'::room_type),('TCL2','TCL2','LAB'::room_type),('TCL3','TCL3','LAB'::room_type),('TCL4','TCL4','LAB'::room_type),
    ('Ubuntu1','Ubuntu1','LAB'::room_type),('Ubuntu2','Ubuntu2','LAB'::room_type)
)
insert into rooms (code, name, room_type, capacity, is_active)
select seed.code, seed.name, seed.room_type, 0, true
from seed
on conflict (code)
do update set
  name = excluded.name,
  room_type = excluded.room_type,
  capacity = excluded.capacity,
  is_active = excluded.is_active;

-- ---------- Track → Subject mapping ----------
with p as (
  select id as program_id from programs where code = 'CSE'
),
s as (
  select id as subject_id, code
  from subjects
  where program_id = (select program_id from p)
    and semester = 6
),
seed(track, subject_code, is_elective) as (
  values
    -- CORE mandatory
    ('CORE'::section_track, 'TCS601', false),
    ('CORE'::section_track, 'TCS611', false),
    ('CORE'::section_track, 'TCS614', false),
    ('CORE'::section_track, 'TCS693', false),
    ('CORE'::section_track, 'XCS601', false),
    ('CORE'::section_track, 'PESE600', false),
    ('CORE'::section_track, 'PCS601', false),
    ('CORE'::section_track, 'PCS614', false),
    ('CORE'::section_track, 'PCS693', false),

    -- CORE electives (is_elective=true)
    ('CORE'::section_track, 'TCS692', true),
    ('CORE'::section_track, 'TCS651', true),
    ('CORE'::section_track, 'TCS619', true),
    ('CORE'::section_track, 'TCS695', true),

    -- CYBER mandatory
    ('CYBER'::section_track, 'TCS601', false),
    ('CYBER'::section_track, 'TCS611', false),
    ('CYBER'::section_track, 'TCS693', false),
    ('CYBER'::section_track, 'TCS679', false),
    ('CYBER'::section_track, 'TCS696', false),
    ('CYBER'::section_track, 'TCS695', false),
    ('CYBER'::section_track, 'XCS601', false),
    ('CYBER'::section_track, 'PESE600', false),
    ('CYBER'::section_track, 'PCS601', false),
    ('CYBER'::section_track, 'PCS679', false),
    ('CYBER'::section_track, 'PCS693', false),

    -- AI_DS mandatory
    ('AI_DS'::section_track, 'TCS601', false),
    ('AI_DS'::section_track, 'TCS611', false),
    ('AI_DS'::section_track, 'TCS693', false),
    ('AI_DS'::section_track, 'TCS663', false),
    ('AI_DS'::section_track, 'TCS692', false),
    ('AI_DS'::section_track, 'XCS601', false),
    ('AI_DS'::section_track, 'PESE600', false),
    ('AI_DS'::section_track, 'PCS601', false),
    ('AI_DS'::section_track, 'PCS663', false),
    ('AI_DS'::section_track, 'PCS693', false),

    -- AI_ML mandatory
    ('AI_ML'::section_track, 'TCS601', false),
    ('AI_ML'::section_track, 'TCS611', false),
    ('AI_ML'::section_track, 'TCS693', false),
    ('AI_ML'::section_track, 'TCS666', false),
    ('AI_ML'::section_track, 'TCS692', false),
    ('AI_ML'::section_track, 'XCS601', false),
    ('AI_ML'::section_track, 'PESE600', false),
    ('AI_ML'::section_track, 'PCS601', false),
    ('AI_ML'::section_track, 'PCS666', false),
    ('AI_ML'::section_track, 'PCS693', false)
)
insert into track_subjects (program_id, semester, track, subject_id, is_elective, sessions_override)
select (select program_id from p), 6, seed.track, s.subject_id, seed.is_elective, null::int
from seed
join s on s.code = seed.subject_code
on conflict (program_id, semester, track, subject_id)
do update set
  is_elective = excluded.is_elective,
  sessions_override = excluded.sessions_override;

commit;
