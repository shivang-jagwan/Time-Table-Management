from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

DAYS_PER_WEEK = 5
PERIODS_PER_DAY = 8
TOTAL_WEEKLY_SLOTS = DAYS_PER_WEEK * PERIODS_PER_DAY


def is_lab(subject: dict) -> bool:
    return str(subject.get("type", "")).upper() == "LAB"


def slot_weight(subject: dict) -> int:
    sessions = int(subject["sessions_per_week"])
    if is_lab(subject):
        return sessions * int(subject.get("lab_block_size_slots", 2))
    return sessions


def teacher_name(i: int) -> str:
    first = [
        "Aarav",
        "Ananya",
        "Vivaan",
        "Diya",
        "Aditya",
        "Isha",
        "Karan",
        "Meera",
        "Rohan",
        "Sana",
        "Nikhil",
        "Priya",
        "Arjun",
        "Neha",
        "Harsh",
        "Ritika",
        "Dev",
        "Kavya",
        "Ishaan",
        "Pooja",
    ]
    last = [
        "Sharma",
        "Verma",
        "Singh",
        "Gupta",
        "Joshi",
        "Mehta",
        "Rao",
        "Mishra",
        "Kapoor",
        "Nair",
        "Banerjee",
        "Yadav",
        "Iyer",
        "Das",
        "Patel",
    ]
    return f"{first[i % len(first)]} {last[(i // len(first)) % len(last)]}"


def build_subjects() -> list[dict]:
    y2 = [
        {"id": "CS201", "name": "Data Structures", "type": "THEORY", "sessions_per_week": 5, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS202", "name": "Computer Organization", "type": "THEORY", "sessions_per_week": 5, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS203", "name": "Discrete Mathematics", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS204", "name": "Object Oriented Programming", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS205", "name": "Database Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS206", "name": "Operating Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "CS207", "name": "Probability and Statistics", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 2, "is_elective": False},
        {"id": "HS201", "name": "Communication Skills", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "lecture_hall", "academic_year": 2, "is_elective": False},
        {"id": "HS202", "name": "Engineering Ethics", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "lecture_hall", "academic_year": 2, "is_elective": False},
        {"id": "CSL201", "name": "Data Structures Lab", "type": "LAB", "sessions_per_week": 3, "lab_block_size_slots": 2, "requires_room_type": "lab", "academic_year": 2, "is_elective": False},
        {"id": "CSL202", "name": "OOP Lab", "type": "LAB", "sessions_per_week": 3, "lab_block_size_slots": 2, "requires_room_type": "lab", "academic_year": 2, "is_elective": False},
        {"id": "EL2AI", "name": "Artificial Intelligence", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
        {"id": "EL2ML", "name": "Machine Learning", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
        {"id": "EL2IOT", "name": "Internet of Things", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
        {"id": "EL2CV", "name": "Computer Vision", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
        {"id": "EL2AR", "name": "AR/VR Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
        {"id": "EL2DV", "name": "DevOps Fundamentals", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 2, "is_elective": True, "elective_block_id": "E2B1"},
    ]

    y3 = [
        {"id": "CS301", "name": "Design and Analysis of Algorithms", "type": "THEORY", "sessions_per_week": 5, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS302", "name": "Computer Networks", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS303", "name": "Software Engineering", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS304", "name": "Compiler Design", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS305", "name": "Distributed Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS306", "name": "Information Security", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS307", "name": "Data Warehousing", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "CS308", "name": "Mobile App Development", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "classroom", "academic_year": 3, "is_elective": False},
        {"id": "HS301", "name": "Professional Practice", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "lecture_hall", "academic_year": 3, "is_elective": False},
        {"id": "HS302", "name": "Research Methodology", "type": "THEORY", "sessions_per_week": 3, "requires_room_type": "lecture_hall", "academic_year": 3, "is_elective": False},
        {"id": "CSL301", "name": "Networks Lab", "type": "LAB", "sessions_per_week": 3, "lab_block_size_slots": 2, "requires_room_type": "lab", "academic_year": 3, "is_elective": False},
        {"id": "CSL302", "name": "Security Lab", "type": "LAB", "sessions_per_week": 3, "lab_block_size_slots": 2, "requires_room_type": "lab", "academic_year": 3, "is_elective": False},
        {"id": "EL3CLD", "name": "Cloud Computing", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B1"},
        {"id": "EL3CYB", "name": "Cyber Security Analytics", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B1"},
        {"id": "EL3SRE", "name": "Site Reliability Engineering", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B1"},
        {"id": "EL3EDA", "name": "Edge AI Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B1"},
        {"id": "EL3BDT", "name": "Big Data Engineering", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B2"},
        {"id": "EL3BLC", "name": "Blockchain Systems", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B2"},
        {"id": "EL3QNT", "name": "Quantum Computing Basics", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B2"},
        {"id": "EL3NLP", "name": "NLP Applications", "type": "THEORY", "sessions_per_week": 4, "requires_room_type": "classroom", "academic_year": 3, "is_elective": True, "elective_block_id": "E3B2"},
    ]
    return y2 + y3


def build_rooms() -> list[dict]:
    rooms: list[dict] = []

    for i in range(1, 19):
        rooms.append(
            {
                "id": f"R-C{i:02d}",
                "name": f"Classroom C{i:02d}",
                "type": "classroom",
                "capacity": 72,
            }
        )

    lab_defs = [
        ("R-L01", "CS Lab 1", "lab", "CS"),
        ("R-L02", "CS Lab 2", "lab", "CS"),
        ("R-L03", "Microprocessor Lab", "lab", "Microprocessor"),
        ("R-L04", "Physics Computing Lab", "lab", "Physics"),
        ("R-L05", "AI Lab", "lab", "AI"),
        ("R-L06", "IoT Systems Lab", "lab", "IoT"),
    ]
    for rid, name, rtype, spec in lab_defs:
        rooms.append({"id": rid, "name": name, "type": rtype, "specialization": spec, "capacity": 48})

    rooms.append({"id": "R-H01", "name": "Lecture Hall Alpha", "type": "lecture_hall", "capacity": 140})
    rooms.append({"id": "R-H02", "name": "Lecture Hall Beta", "type": "lecture_hall", "capacity": 140})

    return rooms


def build_sections() -> list[dict]:
    sections: list[dict] = []

    for i in range(1, 19):
        sections.append(
            {
                "id": f"2A{i}",
                "name": f"Second Year Section {i}",
                "academic_year": 2,
                "program": "CSE",
                "strength": 66 + (i % 6),
            }
        )

    for i in range(1, 25):
        sections.append(
            {
                "id": f"3A{i}",
                "name": f"Third Year Section {i}",
                "academic_year": 3,
                "program": "CSE",
                "strength": 62 + (i % 8),
            }
        )

    return sections


def build_curriculum(subjects_by_id: dict[str, dict], sections: list[dict]) -> tuple[list[dict], list[dict]]:
    y2_optional = ["CS203", "CS206", "CS207", "HS201", "HS202"]
    y2_mandatory = ["CS201", "CS202", "CS204", "CS205", "CSL201", "CSL202"]
    y2_electives = ["EL2AI", "EL2ML", "EL2IOT", "EL2CV", "EL2AR", "EL2DV"]

    y3_optional = ["CS303", "CS304", "CS306", "CS307", "CS308", "HS302"]
    y3_mandatory = ["CS301", "CS302", "CS305", "CSL301", "CSL302", "HS301"]
    y3_e1 = ["EL3CLD", "EL3CYB", "EL3SRE", "EL3EDA"]
    y3_e2 = ["EL3BDT", "EL3BLC", "EL3QNT", "EL3NLP"]

    section_curriculum: list[dict] = []
    tasks: list[dict] = []

    for sec in sections:
        sec_id = sec["id"]
        if sec["academic_year"] == 2:
            idx = int(sec_id.replace("2A", "")) - 1
            core = list(y2_mandatory)
            if idx % 2 == 0:
                core.append(y2_optional[idx % len(y2_optional)])

            chosen = y2_electives[idx % len(y2_electives)]
            elective_choices = [{"block_id": "E2B1", "chosen_subject": chosen}]
        else:
            idx = int(sec_id.replace("3A", "")) - 1
            core = list(y3_mandatory)
            if idx % 3 != 0:
                core.append(y3_optional[idx % len(y3_optional)])

            elective_choices = [
                {"block_id": "E3B1", "chosen_subject": y3_e1[idx % len(y3_e1)]},
                {"block_id": "E3B2", "chosen_subject": y3_e2[(idx + 1) % len(y3_e2)]},
            ]

        session_load = 0
        slot_load = 0

        for subj_id in core:
            subj = subjects_by_id[subj_id]
            ssn = int(subj["sessions_per_week"])
            wt = slot_weight(subj)
            session_load += ssn
            slot_load += wt
            tasks.append(
                {
                    "section_id": sec_id,
                    "academic_year": sec["academic_year"],
                    "subject_id": subj_id,
                    "sessions": ssn,
                    "slot_weight": wt,
                    "is_elective": False,
                    "elective_block_id": None,
                }
            )

        for e in elective_choices:
            subj = subjects_by_id[e["chosen_subject"]]
            ssn = int(subj["sessions_per_week"])
            wt = slot_weight(subj)
            session_load += ssn
            slot_load += wt
            tasks.append(
                {
                    "section_id": sec_id,
                    "academic_year": sec["academic_year"],
                    "subject_id": e["chosen_subject"],
                    "sessions": ssn,
                    "slot_weight": wt,
                    "is_elective": True,
                    "elective_block_id": e["block_id"],
                }
            )

        section_curriculum.append(
            {
                "section_id": sec_id,
                "academic_year": sec["academic_year"],
                "core_subjects": core,
                "elective_blocks": elective_choices,
                "weekly_sessions_total": session_load,
                "weekly_slot_load": slot_load,
            }
        )

    return section_curriculum, tasks


def assign_teachers(subjects: list[dict], tasks: list[dict]) -> tuple[list[dict], dict[str, list[str]], list[dict]]:
    subject_ids = [s["id"] for s in subjects]
    subject_by_id = {s["id"]: s for s in subjects}
    tasks_by_subject: dict[str, list[dict]] = defaultdict(list)
    demand_slots: dict[str, int] = defaultdict(int)

    for t in tasks:
        tasks_by_subject[t["subject_id"]].append(t)
        demand_slots[t["subject_id"]] += int(t["slot_weight"])

    teacher_ids = [f"T{101 + i}" for i in range(74)]
    teachers: list[dict] = []
    for i, tid in enumerate(teacher_ids):
        teachers.append(
            {
                "id": tid,
                "name": teacher_name(i),
                "max_preferred_load": 24 + (i % 7),
                "min_preferred_load": 20,
            }
        )

    teacher_subjects: dict[str, list[str]] = {tid: [] for tid in teacher_ids}
    subject_teachers: dict[str, list[str]] = {sid: [] for sid in subject_ids}

    # Pass 1: at least one teacher per subject.
    for sid, tid in zip(subject_ids, teacher_ids):
        subject_teachers[sid].append(tid)
        teacher_subjects[tid].append(sid)

    # Pass 2: remaining teachers assigned by highest pressure demand.
    remaining = teacher_ids[len(subject_ids):]
    for tid in remaining:
        best_sid = max(subject_ids, key=lambda x: demand_slots[x] / max(1, len(subject_teachers[x])))
        subject_teachers[best_sid].append(tid)
        teacher_subjects[tid].append(best_sid)

    elective_subjects = [s["id"] for s in subjects if s.get("is_elective")]

    # Ensure elective subjects have at least 2 teachers where possible.
    for sid in elective_subjects:
        while len(subject_teachers[sid]) < 2:
            candidates = [t for t in teacher_ids if sid not in teacher_subjects[t] and len(teacher_subjects[t]) < 2]
            if not candidates:
                break
            cid = min(candidates, key=lambda t: len(teacher_subjects[t]))
            subject_teachers[sid].append(cid)
            teacher_subjects[cid].append(sid)

    def run_assignment() -> tuple[dict[str, int], dict[str, int], list[dict]]:
        teacher_load_slots: dict[str, int] = {tid: 0 for tid in teacher_ids}
        teacher_load_sessions: dict[str, int] = {tid: 0 for tid in teacher_ids}
        assignments: list[dict] = []

        for sid in subject_ids:
            queue = sorted(tasks_by_subject[sid], key=lambda x: x["section_id"])
            pool = subject_teachers[sid]
            for q in queue:
                tid = min(pool, key=lambda t: (teacher_load_slots[t], teacher_load_sessions[t], t))
                teacher_load_slots[tid] += int(q["slot_weight"])
                teacher_load_sessions[tid] += int(q["sessions"])
                assignments.append(
                    {
                        "section_id": q["section_id"],
                        "academic_year": q["academic_year"],
                        "subject_id": sid,
                        "teacher_id": tid,
                        "is_elective": q["is_elective"],
                        "elective_block_id": q["elective_block_id"],
                        "combined_class_id": None,
                    }
                )

        return teacher_load_slots, teacher_load_sessions, assignments

    # Balancing pass: underloaded teachers can take one additional high-pressure subject.
    for _ in range(20):
        load_slots, _load_sessions, _assignments = run_assignment()
        under = [t for t in teacher_ids if load_slots[t] < 20 and len(teacher_subjects[t]) < 2]
        if not under:
            break

        subject_pressure = {
            sid: demand_slots[sid] / max(1, len(subject_teachers[sid])) for sid in subject_ids
        }

        changed = False
        for tid in under:
            cand = [sid for sid in subject_ids if sid not in teacher_subjects[tid] and subject_pressure[sid] > 20]
            if not cand:
                continue
            sid = max(cand, key=lambda x: subject_pressure[x])
            subject_teachers[sid].append(tid)
            teacher_subjects[tid].append(sid)
            changed = True

        if not changed:
            break

    final_load_slots, final_load_sessions, assignments = run_assignment()

    for t in teachers:
        tid = t["id"]
        t["subjects"] = teacher_subjects[tid]
        t["assigned_load_slots"] = final_load_slots[tid]
        t["assigned_load_sessions"] = final_load_sessions[tid]

    mapping = [{"teacher_id": t["id"], "subjects": t["subjects"]} for t in teachers]
    return teachers, subject_teachers, assignments


def apply_combined_classes(
    assignments: list[dict],
    subjects_by_id: dict[str, dict],
    subject_teachers: dict[str, list[str]],
) -> tuple[list[dict], list[dict]]:
    combined = [
        {"combined_id": "CG-Y2-01", "subject_id": "CS202", "sections": ["2A1", "2A2", "2A3"]},
        {"combined_id": "CG-Y3-01", "subject_id": "HS301", "sections": ["3A1", "3A2"]},
        {"combined_id": "CG-Y3-02", "subject_id": "CS302", "sections": ["3A5", "3A6", "3A7"]},
    ]

    # Pick combined teacher from subject pool for stability.
    for cg in combined:
        pool = subject_teachers.get(cg["subject_id"], [])
        cg_teacher = pool[0] if pool else None
        cg["teacher_id"] = cg_teacher
        cg["sessions_per_week"] = int(subjects_by_id[cg["subject_id"]]["sessions_per_week"])

    key_to_combined = {}
    for cg in combined:
        for sec in cg["sections"]:
            key_to_combined[(sec, cg["subject_id"])] = cg

    for a in assignments:
        key = (a["section_id"], a["subject_id"])
        if key in key_to_combined:
            cg = key_to_combined[key]
            a["combined_class_id"] = cg["combined_id"]
            if cg.get("teacher_id"):
                a["teacher_id"] = cg["teacher_id"]

    return assignments, combined


def build_elective_blocks(subjects: list[dict], subject_teachers: dict[str, list[str]]) -> list[dict]:
    blocks: dict[str, dict] = {}
    for s in subjects:
        bid = s.get("elective_block_id")
        if not bid:
            continue
        if bid not in blocks:
            blocks[bid] = {
                "block_id": bid,
                "academic_year": s["academic_year"],
                "subjects": [],
                "teachers": set(),
            }
        blocks[bid]["subjects"].append(s["id"])
        for tid in subject_teachers.get(s["id"], []):
            blocks[bid]["teachers"].add(tid)

    out = []
    for bid, val in sorted(blocks.items(), key=lambda x: x[0]):
        out.append(
            {
                "block_id": bid,
                "academic_year": val["academic_year"],
                "subjects": sorted(val["subjects"]),
                "teachers": sorted(list(val["teachers"])),
            }
        )
    return out


def validate_dataset(
    subjects: list[dict],
    rooms: list[dict],
    sections: list[dict],
    curriculum: list[dict],
    assignments: list[dict],
    subject_teachers: dict[str, list[str]],
    elective_blocks: list[dict],
    combined_classes: list[dict],
) -> dict:
    subject_by_id = {s["id"]: s for s in subjects}

    no_teacher_subjects = [sid for sid, ts in subject_teachers.items() if len(ts) == 0]

    section_overloads = [
        {
            "section_id": c["section_id"],
            "weekly_slot_load": c["weekly_slot_load"],
        }
        for c in curriculum
        if int(c["weekly_slot_load"]) > TOTAL_WEEKLY_SLOTS
    ]

    lab_rooms = [r for r in rooms if r.get("type") == "lab"]
    invalid_labs = []
    for s in subjects:
        if s.get("type") == "LAB":
            if int(s.get("lab_block_size_slots", 0)) != 2:
                invalid_labs.append({"subject_id": s["id"], "issue": "lab_block_size_slots != 2"})
            if s.get("requires_room_type") != "lab":
                invalid_labs.append({"subject_id": s["id"], "issue": "requires_room_type != lab"})

    block_subject_set = {b["block_id"]: set(b["subjects"]) for b in elective_blocks}
    elective_inconsistency = []
    for c in curriculum:
        for b in c["elective_blocks"]:
            bid = b["block_id"]
            subj = b["chosen_subject"]
            if subj not in block_subject_set.get(bid, set()):
                elective_inconsistency.append({"section_id": c["section_id"], "block_id": bid, "chosen_subject": subj})

    # Teacher load with combined classes counted as one event per group.
    combined_keys = set()
    for cg in combined_classes:
        for sec in cg["sections"]:
            combined_keys.add((cg["combined_id"], sec, cg["subject_id"]))

    teacher_load_slots = defaultdict(int)
    teacher_load_sessions = defaultdict(int)

    # Non-combined assignments count per section.
    for a in assignments:
        if a.get("combined_class_id"):
            continue
        subj = subject_by_id[a["subject_id"]]
        teacher_load_slots[a["teacher_id"]] += slot_weight(subj)
        teacher_load_sessions[a["teacher_id"]] += int(subj["sessions_per_week"])

    # Combined classes count once per group for teacher load.
    for cg in combined_classes:
        subj = subject_by_id[cg["subject_id"]]
        teacher_load_slots[cg["teacher_id"]] += slot_weight(subj)
        teacher_load_sessions[cg["teacher_id"]] += int(subj["sessions_per_week"])

    teacher_rows = []
    for tid in sorted({a["teacher_id"] for a in assignments} | {cg["teacher_id"] for cg in combined_classes}):
        teacher_rows.append(
            {
                "teacher_id": tid,
                "load_slots": int(teacher_load_slots[tid]),
                "load_sessions": int(teacher_load_sessions[tid]),
            }
        )

    max_teacher = max((r["load_slots"] for r in teacher_rows), default=0)
    min_teacher = min((r["load_slots"] for r in teacher_rows), default=0)
    avg_teacher = round(sum(r["load_slots"] for r in teacher_rows) / max(1, len(teacher_rows)), 2)

    very_overloaded = [r for r in teacher_rows if r["load_slots"] > 35]
    very_underloaded = [r for r in teacher_rows if r["load_slots"] < 12]

    y2_sections = [s for s in sections if s["academic_year"] == 2]
    y3_sections = [s for s in sections if s["academic_year"] == 3]

    return {
        "checks": {
            "no_subject_without_teacher": len(no_teacher_subjects) == 0,
            "section_weekly_slot_limit_ok": len(section_overloads) == 0,
            "lab_definitions_valid": len(invalid_labs) == 0 and len(lab_rooms) >= 1,
            "elective_blocks_consistent": len(elective_inconsistency) == 0,
            "teacher_not_extremely_overloaded": len(very_overloaded) == 0,
        },
        "issues": {
            "subjects_without_teachers": no_teacher_subjects,
            "section_overloads": section_overloads,
            "invalid_labs": invalid_labs,
            "elective_inconsistency": elective_inconsistency,
            "teachers_over_35_slots": very_overloaded,
            "teachers_under_12_slots": very_underloaded,
        },
        "summary": {
            "sections_total": len(sections),
            "sections_year2": len(y2_sections),
            "sections_year3": len(y3_sections),
            "subjects_total": len(subjects),
            "teachers_total": len(teacher_rows),
            "rooms_total": len(rooms),
            "teacher_load_slots_min": min_teacher,
            "teacher_load_slots_max": max_teacher,
            "teacher_load_slots_avg": avg_teacher,
            "recommendation": "Solve year-wise (Year 2 and Year 3 separately) for strong room feasibility margins.",
        },
    }


def main() -> int:
    subjects = build_subjects()
    subjects_by_id = {s["id"]: s for s in subjects}
    rooms = build_rooms()
    sections = build_sections()

    section_curriculum, tasks = build_curriculum(subjects_by_id, sections)
    teachers, subject_teachers, section_teacher_assignments = assign_teachers(subjects, tasks)
    section_teacher_assignments, combined_classes = apply_combined_classes(
        section_teacher_assignments, subjects_by_id, subject_teachers
    )
    elective_blocks = build_elective_blocks(subjects, subject_teachers)

    validation = validate_dataset(
        subjects,
        rooms,
        sections,
        section_curriculum,
        section_teacher_assignments,
        subject_teachers,
        elective_blocks,
        combined_classes,
    )

    dataset = {
        "institution": {
            "days_per_week": DAYS_PER_WEEK,
            "periods_per_day": PERIODS_PER_DAY,
            "total_weekly_slots_per_section": TOTAL_WEEKLY_SLOTS,
        },
        "teachers": teachers,
        "rooms": rooms,
        "subjects": subjects,
        "sections": sections,
        "section_curriculum": section_curriculum,
        "elective_blocks": elective_blocks,
        "combined_classes": combined_classes,
        "teacher_subject_mapping": [
            {"teacher_id": t["id"], "subjects": t["subjects"]} for t in teachers
        ],
        "section_teacher_assignments": section_teacher_assignments,
        "validation": validation,
    }

    out = Path(__file__).resolve().parent / "outputs" / "solver_dataset_complete_y2_y3.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dataset, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"WROTE: {out}")
    print(json.dumps(validation["summary"], indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
