from __future__ import annotations

"""
Diagnostic: seed tenant-scoped 3-year dataset with low room capacity, then solve globally.

Goals:
- Login via cookie auth using provided admin credentials
- Ensure academic years 1..3
- Ensure program (CSE)
- Generate Mon–Fri time slots (8 x 60min)
- Create few rooms (high utilization: 2 classrooms + 1 lab)
- Create teachers with reasonable constraints
- Create subjects (mix of THEORY + LAB) per year
- Create 6 sections per year (A..F)
- Map CORE track subjects
- Strict teacher-subject-section assignments
- Set default section windows across Mon–Fri slots
- Run generate-global + solve-global
- Print summary: counts, room utilization, conflicts/warnings

This script uses FastAPI TestClient and is tenant-safe (TENANT_MODE=per_user).
"""

import os
import sys
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from main import app


# Configurable admin credentials via env with defaults matching the prompt.
ADMIN_USERNAME = os.environ.get("DIAG_ADMIN_USERNAME", "DeepaliDon")
ADMIN_PASSWORD = os.environ.get("DIAG_ADMIN_PASSWORD", "Deepalidon@always")


DAY = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
}


@dataclass
class SubjectSpec:
    year: int
    code: str
    name: str
    subject_type: str  # THEORY | LAB
    sessions_per_week: int
    max_per_day: int
    lab_block_size_slots: int


@dataclass
class TeacherSpec:
    code: str
    full_name: str
    weekly_off_day: int | None
    max_per_day: int
    max_per_week: int
    max_continuous: int


def _ensure_ok(resp, *, context: str = ""):
    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text
        raise RuntimeError(f"API error {context}: {resp.status_code} {payload}")


def _login(client: TestClient) -> None:
    r = client.post("/api/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    _ensure_ok(r, context="login")
    data = r.json()
    if not bool(data.get("ok")):
        raise RuntimeError("Login failed: response not ok")


def _ensure_program(client: TestClient, code: str, name: str) -> str:
    r = client.get("/api/programs/")
    _ensure_ok(r, context="list_programs")
    rows = r.json() or []
    for p in rows:
        if str(p.get("code")) == code:
            return str(p["id"])
    r = client.post("/api/programs/", json={"code": code, "name": name})
    _ensure_ok(r, context="create_program")
    return str(r.json()["id"])


def _ensure_academic_years(client: TestClient, years: list[int]) -> None:
    r = client.post(
        "/api/admin/academic-years/ensure",
        json={"year_numbers": years, "activate": True},
    )
    _ensure_ok(r, context="ensure_academic_years")


def _generate_time_slots(client: TestClient, *, days: list[int], slot_minutes: int = 60) -> None:
    r = client.post(
        "/api/admin/time-slots/generate",
        json={
            "start_time": "08:00",
            "end_time": "16:00",
            "slot_minutes": slot_minutes,
            "days": days,
            "replace_existing": False,
        },
    )
    _ensure_ok(r, context="generate_time_slots")


def _ensure_rooms(client: TestClient, rooms: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    r = client.get("/api/rooms/")
    _ensure_ok(r, context="list_rooms")
    existing = {str(x["code"]).upper(): x for x in (r.json() or [])}
    out: list[dict[str, Any]] = []
    for code, name, room_type in rooms:
        cur = existing.get(code.upper())
        if cur is None:
            r = client.post(
                "/api/rooms/",
                json={
                    "code": code,
                    "name": name,
                    "room_type": room_type,
                    "capacity": 0,
                    "is_active": True,
                    "is_special": False,
                },
            )
            _ensure_ok(r, context=f"create_room:{code}")
            cur = r.json()
        out.append(cur)
    return out


def _ensure_teachers(client: TestClient, teachers: list[TeacherSpec]) -> dict[str, dict[str, Any]]:
    r = client.get("/api/teachers/")
    _ensure_ok(r, context="list_teachers")
    existing = {str(x["code"]).upper(): x for x in (r.json() or [])}
    out: dict[str, dict[str, Any]] = {}
    for t in teachers:
        cur = existing.get(t.code.upper())
        if cur is None:
            r = client.post(
                "/api/teachers/",
                json={
                    "code": t.code,
                    "full_name": t.full_name,
                    "weekly_off_day": t.weekly_off_day,
                    "max_per_day": t.max_per_day,
                    "max_per_week": t.max_per_week,
                    "max_continuous": t.max_continuous,
                    "is_active": True,
                },
            )
            _ensure_ok(r, context=f"create_teacher:{t.code}")
            cur = r.json()
        out[t.code] = cur
    return out


def _ensure_subjects(client: TestClient, program_code: str, subjects: list[SubjectSpec]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    # Fetch per-year to avoid ambiguity
    for year in sorted({s.year for s in subjects}):
        r = client.get(
            "/api/subjects/",
            params={"program_code": program_code, "academic_year_number": year},
        )
        _ensure_ok(r, context=f"list_subjects:Y{year}")
        existing = {str(x["code"]).upper(): x for x in (r.json() or [])}
        for s in [x for x in subjects if x.year == year]:
            cur = existing.get(s.code.upper())
            if cur is None:
                r = client.post(
                    "/api/subjects/",
                    json={
                        "program_code": program_code,
                        "academic_year_number": s.year,
                        "code": s.code,
                        "name": s.name,
                        "subject_type": s.subject_type,
                        "sessions_per_week": s.sessions_per_week,
                        "max_per_day": s.max_per_day,
                        "lab_block_size_slots": s.lab_block_size_slots,
                        "is_active": True,
                    },
                )
                _ensure_ok(r, context=f"create_subject:{s.code}")
                cur = r.json()
            out[s.code] = cur
    return out


def _ensure_sections(client: TestClient, program_code: str, *, year: int, codes: list[str]) -> dict[str, dict[str, Any]]:
    r = client.get("/api/sections/", params={"program_code": program_code, "academic_year_number": year})
    _ensure_ok(r, context=f"list_sections:Y{year}")
    existing = {str(x["code"]).upper(): x for x in (r.json() or [])}
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        cur = existing.get(code.upper())
        if cur is None:
            r = client.post(
                "/api/sections/",
                json={
                    "program_code": program_code,
                    "academic_year_number": year,
                    "code": code,
                    "name": code,
                    "strength": 60,
                    "track": "CORE",
                    "is_active": True,
                },
            )
            _ensure_ok(r, context=f"create_section:{code}")
            cur = r.json()
        out[code] = cur
    return out


def _map_core_track_subjects(
    client: TestClient,
    program_code: str,
    subjects_by_code: dict[str, dict[str, Any]],
    subjects_spec: list[SubjectSpec],
) -> None:
    year_by_code = {s.code: s.year for s in subjects_spec}
    for s_code, s in subjects_by_code.items():
        r = client.post(
            "/api/curriculum/track-subjects",
            json={
                "program_code": program_code,
                "academic_year_number": int(year_by_code.get(s_code, 1)),
                "track": "CORE",
                "subject_code": s_code,
                "is_elective": False,
                "sessions_override": None,
            },
        )
        # TrackSubject uniqueness per (program, year, track, subject). Ignore conflicts silently.
        if r.status_code == 409:
            continue
        _ensure_ok(r, context=f"track_subject:{s_code}")


def _set_default_windows(client: TestClient, program_code: str, *, year: int, days: list[int]) -> None:
    r = client.post(
        "/api/admin/section-windows/set-default",
        json={
            "program_code": program_code,
            "academic_year_number": year,
            "days": days,
            "start_slot_index": 0,
            "end_slot_index": 7,
            "replace_existing": False,
        },
    )
    _ensure_ok(r, context=f"set_default_section_windows:Y{year}")


def _set_teacher_subject_sections(
    client: TestClient,
    *,
    teacher_row: dict[str, Any],
    subject_row: dict[str, Any],
    section_rows: list[dict[str, Any]],
) -> None:
    r = client.put(
        "/api/admin/teacher-subject-sections",
        json={
            "teacher_id": teacher_row["id"],
            "subject_id": subject_row["id"],
            "section_ids": [s["id"] for s in section_rows],
        },
    )
    _ensure_ok(r, context=f"set_tss:{teacher_row['code']}:{subject_row['code']}")


def _clear_teacher_subject_sections(
    client: TestClient,
    *,
    teacher_row: dict[str, Any],
    subject_row: dict[str, Any],
) -> None:
    # Deactivate all existing assignments for this (teacher, subject)
    r = client.put(
        "/api/admin/teacher-subject-sections",
        json={
            "teacher_id": teacher_row["id"],
            "subject_id": subject_row["id"],
            "section_ids": [],
        },
    )
    _ensure_ok(r, context=f"clear_tss:{teacher_row['code']}:{subject_row['code']}")


def _solve_global(client: TestClient, program_code: str, *, max_time_seconds: float = 180.0) -> dict[str, Any]:
    r = client.post("/api/solver/generate-global", json={"program_code": program_code})
    _ensure_ok(r, context="generate_global")
    gen = r.json()

    r = client.post(
        "/api/solver/solve-global",
        json={
            "program_code": program_code,
            "max_time_seconds": max_time_seconds,
            "relax_teacher_load_limits": False,
            "require_optimal": False,
        },
    )
    _ensure_ok(r, context="solve_global")
    return r.json()


def _run() -> int:
    client = TestClient(app)
    _login(client)

    program_code = "CSE"
    program_name = "Computer Science & Engineering"

    years = [1, 2, 3]
    _ensure_academic_years(client, years)
    _generate_time_slots(client, days=[DAY["MON"], DAY["TUE"], DAY["WED"], DAY["THU"], DAY["FRI"]])
    program_id = _ensure_program(client, program_code, program_name)

    # High utilization: few rooms
    rooms = _ensure_rooms(
        client,
        rooms=[
            ("CR101", "CR101", "CLASSROOM"),
            ("CR102", "CR102", "CLASSROOM"),
            ("CR103", "CR103", "CLASSROOM"),
            ("LAB1", "LAB1", "LAB"),
        ],
    )

    teachers = _ensure_teachers(
        client,
        teachers=[
            # Mon–Fri schedule; set off day to SAT to keep constraints valid when needed.
            TeacherSpec("T1", "T1", DAY["SAT"], 4, 20, 3),
            TeacherSpec("T2", "T2", DAY["SAT"], 4, 20, 3),
            TeacherSpec("T3", "T3", DAY["SAT"], 4, 20, 3),
            TeacherSpec("T4", "T4", DAY["SAT"], 4, 20, 3),
            # Additional theory instructors to keep weekly load under 30
            TeacherSpec("T5", "T5", DAY["SAT"], 5, 30, 3),
            TeacherSpec("T6", "T6", DAY["SAT"], 5, 30, 3),
            # Lab instructor with higher continuous capacity
            TeacherSpec("T8", "T8", None, 6, 30, 4),
            # Additional lab instructor to distribute weekly load
            TeacherSpec("T9", "T9", None, 6, 30, 4),
        ],
    )

    subjects_spec: list[SubjectSpec] = [
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
        SubjectSpec(3, "OS-LAB", "OS-LAB", "LAB", 1, 1, 2),
    ]

    subjects = _ensure_subjects(client, program_code, subjects_spec)
    _map_core_track_subjects(client, program_code, subjects, subjects_spec)

    # Sections A..F for each year
    sections_by_year: dict[int, dict[str, dict[str, Any]]] = {}
    for y in years:
        codes = [f"Y{y}-{c}" for c in ["A", "B", "C", "D", "E", "F"]]
        sections_by_year[y] = _ensure_sections(client, program_code, year=y, codes=codes)

    # Default windows across Mon–Fri
    for y in years:
        _set_default_windows(client, program_code, year=y, days=[DAY[d] for d in ["MON", "TUE", "WED", "THU", "FRI"]])

    # Strict teacher-subject-section assignments
    def _rows(d: dict[str, dict[str, Any]], names: list[str]) -> list[dict[str, Any]]:
        return [d[n] for n in names]

    # Year 1
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T1"],
        subject_row=subjects["MATH1"],
        section_rows=_rows(sections_by_year[1], list(sections_by_year[1].keys())),
    )
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T2"],
        subject_row=subjects["PROG1"],
        section_rows=_rows(sections_by_year[1], list(sections_by_year[1].keys())),
    )
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T8"],
        subject_row=subjects["PROG1-LAB"],
        section_rows=_rows(sections_by_year[1], list(sections_by_year[1].keys())),
    )

    # Year 2
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T3"],
        subject_row=subjects["DS"],
        section_rows=_rows(sections_by_year[2], list(sections_by_year[2].keys())),
    )
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T4"],
        subject_row=subjects["DB"],
        section_rows=_rows(sections_by_year[2], list(sections_by_year[2].keys())),
    )
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T8"],
        subject_row=subjects["DB-LAB"],
        section_rows=_rows(sections_by_year[2], list(sections_by_year[2].keys())),
    )

    # Year 3
    _clear_teacher_subject_sections(client, teacher_row=teachers["T3"], subject_row=subjects["OS"])  # switch from T3 -> T5
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T5"],
        subject_row=subjects["OS"],
        section_rows=_rows(sections_by_year[3], list(sections_by_year[3].keys())),
    )
    _clear_teacher_subject_sections(client, teacher_row=teachers["T4"], subject_row=subjects["CN"])  # switch from T4 -> T6
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T6"],
        subject_row=subjects["CN"],
        section_rows=_rows(sections_by_year[3], list(sections_by_year[3].keys())),
    )
    _clear_teacher_subject_sections(client, teacher_row=teachers["T8"], subject_row=subjects["OS-LAB"])  # switch from T8 -> T9
    _set_teacher_subject_sections(
        client,
        teacher_row=teachers["T9"],
        subject_row=subjects["OS-LAB"],
        section_rows=_rows(sections_by_year[3], list(sections_by_year[3].keys())),
    )

    # Solve
    solve = _solve_global(client, program_code)
    run_id = solve.get("run_id")
    status = str(solve.get("status"))
    entries_written = int(solve.get("entries_written") or 0)
    conflicts = solve.get("conflicts") or []
    warnings = solve.get("warnings") or []

    # Fetch entries to compute utilization metrics
    entries: list[dict[str, Any]] = []
    if run_id:
        r = client.get(f"/api/solver/runs/{run_id}/entries")
        _ensure_ok(r, context="list_run_entries")
        entries = (r.json() or {}).get("entries") or []

    # Utilization: approximate occupancy ratio and peak concurrent entries per slot
    # Gather slot/day stats
    slot_keys = [(e.get("day_of_week"), e.get("slot_index")) for e in entries]
    peak_concurrent = 0
    slots_count: dict[tuple[int, int], int] = {}
    for k in slot_keys:
        slots_count[k] = slots_count.get(k, 0) + 1
        if slots_count[k] > peak_concurrent:
            peak_concurrent = slots_count[k]

    # Capacity baseline: rooms_count * (days * slots)
    rooms_count = len(rooms)
    days = 5
    slots_per_day = 8
    capacity_slots = rooms_count * days * slots_per_day
    utilization_ratio = (len(entries) / capacity_slots) if capacity_slots > 0 else 0.0

    print({
        "status": status,
        "run_id": str(run_id) if run_id else None,
        "entries_written": entries_written,
        "total_entries": len(entries),
        "peak_concurrent": peak_concurrent,
        "utilization_ratio": round(utilization_ratio, 4),
        "conflicts_count": len(conflicts),
        "warnings_count": len(warnings),
        "conflict_types": sorted({str(c.get("conflict_type")) for c in conflicts}) if conflicts else [],
        "conflicts_summary": [
            {
                "type": str(c.get("conflict_type")),
                "teacher": (c.get("metadata") or {}).get("teacher_name"),
                "assigned_slots": (c.get("metadata") or {}).get("assigned_slots"),
                "difference": (c.get("metadata") or {}).get("difference"),
            }
            for c in conflicts
            if str(c.get("conflict_type")) == "TEACHER_LOAD_EXCEEDS_MAX_PER_WEEK"
        ],
    })

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_run())
    except Exception as exc:
        print({"error": str(exc)})
        raise
