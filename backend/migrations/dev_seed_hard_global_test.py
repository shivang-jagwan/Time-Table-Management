from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

import psycopg2


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


DAY = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
}


@dataclass(frozen=True)
class SubjectSpec:
    year: int
    code: str
    name: str
    subject_type: str  # THEORY | LAB
    sessions_per_week: int
    max_per_day: int
    lab_block_size_slots: int


@dataclass(frozen=True)
class TeacherSpec:
    code: str
    full_name: str
    weekly_off_day: int | None
    max_per_day: int
    max_per_week: int
    max_continuous: int


def _upsert_returning_id(cur, sql: str, params: tuple) -> str:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError("Expected RETURNING id")
    return str(row[0])


def _get_id(cur, sql: str, params: tuple) -> str:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"Missing row for query: {sql} params={params}")
    return str(row[0])


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    conninfo = _normalize_psycopg_url(database_url)

    program_code = "CSE"
    program_name = "Computer Science & Engineering"

    years = [1, 2, 3]

    rooms = [
        ("CR101", "CR101", "CLASSROOM"),
        ("CR102", "CR102", "CLASSROOM"),
        ("LAB1", "LAB1", "LAB"),
        ("LAB2", "LAB2", "LAB"),
        ("SR1", "SR1", "LT"),
    ]

    # 8:00–4:00 (8 slots of 60 minutes) Mon–Fri
    slot_minutes = 60
    days = [DAY["MON"], DAY["TUE"], DAY["WED"], DAY["THU"], DAY["FRI"]]

    subjects: list[SubjectSpec] = [
        # Year 1
        SubjectSpec(1, "MATH1", "MATH1", "THEORY", 3, 1, 1),
        SubjectSpec(1, "PROG1", "PROG1", "THEORY", 3, 1, 1),
        SubjectSpec(1, "PROG1-LAB", "PROG1-LAB", "LAB", 1, 1, 2),
        # Year 2
        SubjectSpec(2, "DS", "DS", "THEORY", 3, 1, 1),
        SubjectSpec(2, "DB", "DB", "THEORY", 3, 1, 1),
        SubjectSpec(2, "DB-LAB", "DB-LAB", "LAB", 1, 1, 2),
        # Year 3
        SubjectSpec(3, "OS", "OS", "THEORY", 3, 1, 1),
        SubjectSpec(3, "CN", "CN", "THEORY", 3, 1, 1),
        SubjectSpec(3, "AI", "AI", "THEORY", 3, 1, 1),
        SubjectSpec(3, "OS-LAB", "OS-LAB", "LAB", 1, 1, 2),
        SubjectSpec(3, "CN-LAB", "CN-LAB", "LAB", 1, 1, 2),
    ]

    teachers: list[TeacherSpec] = [
        # Note: this dataset schedules Mon–Fri only. Setting weekly_off_day to SAT keeps the constraint valid
        # while avoiding infeasibility for high-load teachers who would otherwise have only 4 working days.
        TeacherSpec("T1", "T1", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T2", "T2", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T3", "T3", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T4", "T4", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T5", "T5", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T6", "T6", DAY["SAT"], 4, 20, 3),
        TeacherSpec("T7", "T7", DAY["TUE"], 3, 12, 2),
        # Lab instructors: split load so each teacher stays feasible within a 5-day x 8-slot week.
        TeacherSpec("T8", "T8", None, 6, 30, 4),
        TeacherSpec("T10", "T10", None, 6, 30, 4),
        # AI instructor for the combined Y3-D/E/F group.
        TeacherSpec("T9", "T9", DAY["FRI"], 2, 12, 2),
    ]

    section_codes = {
        1: ["Y1-A", "Y1-B", "Y1-C", "Y1-D", "Y1-E", "Y1-F"],
        2: ["Y2-A", "Y2-B", "Y2-C", "Y2-D", "Y2-E", "Y2-F"],
        3: ["Y3-A", "Y3-B", "Y3-C", "Y3-D", "Y3-E", "Y3-F"],
    }

    with psycopg2.connect(conninfo) as conn:
        with conn.cursor() as cur:
            # Program
            program_id = _upsert_returning_id(
                cur,
                """
INSERT INTO programs (code, name)
VALUES (%s, %s)
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
RETURNING id;
""",
                (program_code, program_name),
            )

            # Academic years
            year_ids: dict[int, str] = {}
            for y in years:
                year_ids[y] = _upsert_returning_id(
                    cur,
                    """
INSERT INTO academic_years (year_number, is_active)
VALUES (%s, TRUE)
ON CONFLICT (year_number) DO UPDATE SET is_active = TRUE
RETURNING id;
""",
                    (int(y),),
                )

            # Rooms
            room_ids: dict[str, str] = {}
            for code, name, room_type in rooms:
                room_ids[code] = _upsert_returning_id(
                    cur,
                    """
INSERT INTO rooms (code, name, room_type, capacity, is_active)
VALUES (%s, %s, %s, %s, TRUE)
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  room_type = EXCLUDED.room_type,
  capacity = EXCLUDED.capacity,
  is_active = TRUE
RETURNING id;
""",
                    (code, name, room_type, 0),
                )

            # Time slots
            for d in days:
                for slot_index in range(8):
                    start_h = 8 + slot_index
                    end_h = start_h + 1
                    cur.execute(
                        """
INSERT INTO time_slots (day_of_week, slot_index, start_time, end_time)
VALUES (%s, %s, %s, %s)
ON CONFLICT (day_of_week, slot_index) DO UPDATE SET
  start_time = EXCLUDED.start_time,
  end_time = EXCLUDED.end_time;
""",
                        (int(d), int(slot_index), time(start_h, 0), time(end_h, 0)),
                    )

            # Teachers
            teacher_ids: dict[str, str] = {}
            for t in teachers:
                teacher_ids[t.code] = _upsert_returning_id(
                    cur,
                    """
INSERT INTO teachers (code, full_name, weekly_off_day, max_per_day, max_per_week, max_continuous, is_active)
VALUES (%s, %s, %s, %s, %s, %s, TRUE)
ON CONFLICT (code) DO UPDATE SET
  full_name = EXCLUDED.full_name,
  weekly_off_day = EXCLUDED.weekly_off_day,
  max_per_day = EXCLUDED.max_per_day,
  max_per_week = EXCLUDED.max_per_week,
  max_continuous = EXCLUDED.max_continuous,
  is_active = TRUE
RETURNING id;
""",
                    (
                        t.code,
                        t.full_name,
                        t.weekly_off_day,
                        t.max_per_day,
                        t.max_per_week,
                        t.max_continuous,
                    ),
                )

            # Subjects
            subject_ids: dict[str, str] = {}
            for s in subjects:
                subject_ids[s.code] = _upsert_returning_id(
                    cur,
                    """
INSERT INTO subjects (program_id, academic_year_id, code, name, subject_type, sessions_per_week, max_per_day, lab_block_size_slots, is_active)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
ON CONFLICT (academic_year_id, code) DO UPDATE SET
  program_id = EXCLUDED.program_id,
  name = EXCLUDED.name,
  subject_type = EXCLUDED.subject_type,
  sessions_per_week = EXCLUDED.sessions_per_week,
  max_per_day = EXCLUDED.max_per_day,
  lab_block_size_slots = EXCLUDED.lab_block_size_slots,
  is_active = TRUE
RETURNING id;
""",
                    (
                        program_id,
                        year_ids[s.year],
                        s.code,
                        s.name,
                        s.subject_type,
                        s.sessions_per_week,
                        s.max_per_day,
                        s.lab_block_size_slots,
                    ),
                )

            # Sections
            section_ids: dict[str, str] = {}
            for y, codes in section_codes.items():
                for c in codes:
                    section_ids[c] = _upsert_returning_id(
                        cur,
                        """
INSERT INTO sections (program_id, academic_year_id, code, name, strength, track, is_active)
VALUES (%s, %s, %s, %s, %s, %s, TRUE)
ON CONFLICT (academic_year_id, code) DO UPDATE SET
  program_id = EXCLUDED.program_id,
  name = EXCLUDED.name,
  strength = EXCLUDED.strength,
  track = EXCLUDED.track,
  is_active = TRUE
RETURNING id;
""",
                        (
                            program_id,
                            year_ids[y],
                            c,
                            c,
                            60,
                            "CORE",
                        ),
                    )

            # Curriculum: track_subjects (mandatory)
            # Ensure track_subjects exists and is year-aware.
            for s in subjects:
                cur.execute(
                    """
INSERT INTO track_subjects (program_id, academic_year_id, track, subject_id, is_elective, sessions_override)
VALUES (%s, %s, %s, %s, FALSE, NULL)
ON CONFLICT (program_id, academic_year_id, track, subject_id) DO NOTHING;
""",
                    (program_id, year_ids[s.year], "CORE", subject_ids[s.code]),
                )

            # Section time windows: allow all slots Mon–Fri (0..7)
            all_section_ids = list(section_ids.values())
            if all_section_ids:
                cur.execute(
                    "DELETE FROM section_time_windows WHERE section_id = ANY(%s::uuid[])",
                    (all_section_ids,),
                )
                for sec_code, sec_id in section_ids.items():
                    for d in days:
                        cur.execute(
                            """
INSERT INTO section_time_windows (section_id, day_of_week, start_slot_index, end_slot_index)
VALUES (%s, %s, %s, %s);
""",
                            (sec_id, int(d), 0, 7),
                        )

            # Strict teacher-subject-section assignments
            # Clear any existing assignments for these subjects/sections, then reinsert.
            cur.execute(
                """
DELETE FROM teacher_subject_sections
WHERE subject_id = ANY(%s::uuid[])
    OR section_id = ANY(%s::uuid[]);
""",
                (list(subject_ids.values()), list(section_ids.values())),
            )

            def assign(teacher_code: str, subject_code: str, section_code_list: list[str]):
                tid = teacher_ids[teacher_code]
                sid = subject_ids[subject_code]
                for sc in section_code_list:
                    secid = section_ids[sc]
                    cur.execute(
                        """
INSERT INTO teacher_subject_sections (teacher_id, subject_id, section_id, is_active)
VALUES (%s, %s, %s, TRUE)
ON CONFLICT (teacher_id, subject_id, section_id) DO UPDATE SET is_active = TRUE;
""",
                        (tid, sid, secid),
                    )

            # Year 1
            assign("T1", "MATH1", section_codes[1])
            assign("T2", "PROG1", section_codes[1])
            assign("T8", "PROG1-LAB", section_codes[1])

            # Year 2
            assign("T3", "DS", section_codes[2])
            assign("T4", "DB", section_codes[2])
            assign("T8", "DB-LAB", section_codes[2])

            # Year 3
            assign("T5", "OS", section_codes[3])
            assign("T6", "CN", section_codes[3])
            # Year 3 labs are assigned to a different teacher to keep weekly load feasible.
            assign("T10", "OS-LAB", section_codes[3])
            assign("T10", "CN-LAB", section_codes[3])

            # AI split: T7 for Y3-A/B/C, T9 for Y3-D/E/F (combined group uses those)
            assign("T7", "AI", ["Y3-A", "Y3-B", "Y3-C"])
            assign("T9", "AI", ["Y3-D", "Y3-E", "Y3-F"])

            # Combined group (v2): AI for Y3-D/E/F with explicit teacher
            ai_year_id = year_ids[3]
            ai_subject_id = subject_ids["AI"]
            ai_teacher_id = teacher_ids["T9"]
            cur.execute(
                """
INSERT INTO combined_groups (academic_year_id, subject_id, teacher_id)
VALUES (%s, %s, %s)
ON CONFLICT (id) DO NOTHING
RETURNING id;
""",
                (ai_year_id, ai_subject_id, ai_teacher_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                group_id = str(row[0])
            else:
                group_id = _get_id(
                    cur,
                    "SELECT id FROM combined_groups WHERE academic_year_id = %s AND subject_id = %s AND teacher_id = %s",
                    (ai_year_id, ai_subject_id, ai_teacher_id),
                )

            for sc in ["Y3-D", "Y3-E", "Y3-F"]:
                cur.execute(
                    """
INSERT INTO combined_group_sections (combined_group_id, subject_id, section_id)
VALUES (%s, %s, %s)
ON CONFLICT (combined_group_id, section_id) DO NOTHING;
""",
                    (group_id, ai_subject_id, section_ids[sc]),
                )

            # Special allotment: Y3-A OS locked (avoid T5 weekly off day = Monday)
            slot_id = _get_id(
                cur,
                "SELECT id FROM time_slots WHERE day_of_week = %s AND slot_index = %s",
                (DAY["TUE"], 2),
            )
            # Clear any prior OS special allotment for this section so the lock is unique.
            cur.execute(
                "DELETE FROM special_allotments WHERE section_id = %s AND subject_id = %s",
                (section_ids["Y3-A"], subject_ids["OS"]),
            )
            cur.execute(
                """
INSERT INTO special_allotments (section_id, subject_id, teacher_id, room_id, slot_id, reason, is_active)
VALUES (%s, %s, %s, %s, %s, %s, TRUE);
""",
                (
                    section_ids["Y3-A"],
                    subject_ids["OS"],
                    teacher_ids["T5"],
                    room_ids["SR1"],
                    slot_id,
                    "Hard global test: OS locked in SR1 (Tue slot 2)",
                ),
            )

            # Report counts for this seeded dataset (CSE, Years 1-3).
            cur.execute(
                """
SELECT
  (SELECT count(*) FROM sections WHERE program_id = %s AND academic_year_id = ANY(%s::uuid[])) AS sections,
  (SELECT count(*) FROM subjects WHERE program_id = %s AND academic_year_id = ANY(%s::uuid[])) AS subjects,
  (SELECT count(*) FROM teachers WHERE code = ANY(%s)) AS teachers,
  (SELECT count(*) FROM rooms WHERE code = ANY(%s)) AS rooms,
  (SELECT count(*) FROM time_slots WHERE day_of_week = ANY(%s) AND slot_index BETWEEN 0 AND 7) AS time_slots,
    (SELECT count(*) FROM combined_groups WHERE academic_year_id = %s AND subject_id = %s) AS combined_groups,
  (SELECT count(*) FROM special_allotments WHERE section_id = %s AND slot_id = %s AND is_active IS TRUE) AS special_allotments
""",
                (
                    program_id,
                    [year_ids[y] for y in years],
                    program_id,
                    [year_ids[y] for y in years],
                    [t.code for t in teachers],
                    [r[0] for r in rooms],
                    days,
                    year_ids[3],
                    subject_ids["AI"],
                    section_ids["Y3-A"],
                    slot_id,
                ),
            )
            seeded_counts = cur.fetchone()

    if seeded_counts:
        sections_cnt, subjects_cnt, teachers_cnt, rooms_cnt, slots_cnt, combined_cnt, special_cnt = seeded_counts
        print(
            "OK: seeded hard global test data ("
            f"program={program_code}, years={years}, sections={sections_cnt}, subjects={subjects_cnt}, "
            f"teachers={teachers_cnt}, rooms={rooms_cnt}, time_slots={slots_cnt}, combined_groups={combined_cnt}, "
            f"special_allotments={special_cnt})."
        )
    else:
        print(f"OK: seeded hard global test data (program={program_code}, years={years}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
