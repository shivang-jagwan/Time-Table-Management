#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import time
from pathlib import Path

from sqlalchemy import delete, select, text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal  # noqa: E402
from core.security import hash_password  # noqa: E402
from models.academic_year import AcademicYear  # noqa: E402
from models.combined_group import CombinedGroup  # noqa: E402
from models.combined_group_section import CombinedGroupSection  # noqa: E402
from models.elective_block import ElectiveBlock  # noqa: E402
from models.elective_block_subject import ElectiveBlockSubject  # noqa: E402
from models.program import Program  # noqa: E402
from models.room import Room  # noqa: E402
from models.section import Section  # noqa: E402
from models.section_elective_block import SectionElectiveBlock  # noqa: E402
from models.section_subject import SectionSubject  # noqa: E402
from models.section_time_window import SectionTimeWindow  # noqa: E402
from models.subject import Subject  # noqa: E402
from models.teacher import Teacher  # noqa: E402
from models.teacher_subject_section import TeacherSubjectSection  # noqa: E402
from models.tenant import Tenant  # noqa: E402
from models.time_slot import TimeSlot  # noqa: E402
from models.user import User  # noqa: E402


ROOM_TYPE_MAP = {
    "classroom": "CLASSROOM",
    "lab": "LAB",
    "lecture_hall": "LT",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shivang123")
    parser.add_argument("--password", default="Shivang@GEHU123")
    parser.add_argument(
        "--dataset",
        default=str(Path(__file__).resolve().parent / "outputs" / "solver_dataset_complete_y2_y3.json"),
    )
    parser.add_argument("--reset-existing", action="store_true")
    return parser.parse_args()


def _tenant_delete_order() -> list[str]:
    return [
        "timetable_entries",
        "timetable_conflicts",
        "timetable_runs",
        "fixed_timetable_entries",
        "special_allotments",
        "combined_group_sections",
        "combined_groups",
        "section_elective_blocks",
        "elective_block_subjects",
        "elective_blocks",
        "teacher_subject_sections",
        "section_subjects",
        "section_time_windows",
        "teacher_time_windows",
        "subject_allowed_rooms",
        "curriculum_subjects",
        "track_subjects",
        "sections",
        "subjects",
        "teachers",
        "rooms",
        "time_slots",
        "academic_years",
        "programs",
        "users",
        "tenants",
    ]


def _purge_tenant_rows(db, tenant_id: uuid.UUID) -> None:
    for table in _tenant_delete_order():
        if table == "tenants":
            db.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": str(tenant_id)})
        else:
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": str(tenant_id)})


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"[ERROR] dataset not found: {dataset_path}")
        return 1

    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    db = SessionLocal()
    try:
        existing_user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()

        tenant = None
        if existing_user is not None:
            tenant = db.execute(select(Tenant).where(Tenant.id == existing_user.tenant_id)).scalar_one_or_none()
            if args.reset_existing and tenant is not None:
                tid = tenant.id
                _purge_tenant_rows(db, tid)
                db.commit()
                tenant = None
                existing_user = None

        if tenant is None:
            tenant_slug = f"{args.username}-tenant"
            tenant = db.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalar_one_or_none()

            if tenant is None:
                tenant = Tenant(id=uuid.uuid4(), slug=tenant_slug, name=f"{args.username} Tenant")
                db.add(tenant)
                db.flush()

            if existing_user is None:
                existing_user = User(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    name=args.username,
                    username=args.username,
                    password_hash=hash_password(args.password),
                    role="ADMIN",
                    is_active=True,
                )
                db.add(existing_user)
            else:
                existing_user.tenant_id = tenant.id
                existing_user.password_hash = hash_password(args.password)
                existing_user.role = "ADMIN"
                existing_user.is_active = True

            db.flush()

        tenant_id = tenant.id

        # Clean tenant business data before reseed (keep tenant+user rows).
        for table in _tenant_delete_order():
            if table in {"users", "tenants"}:
                continue
            db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tid"), {"tid": str(tenant_id)})

        db.flush()

        program_code = "CSE"
        program = Program(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code=program_code,
            name="Computer Science and Engineering",
        )
        db.add(program)
        db.flush()

        year_map: dict[int, uuid.UUID] = {}
        for year_number in [2, 3]:
            ay = AcademicYear(id=uuid.uuid4(), tenant_id=tenant_id, year_number=year_number, is_active=True)
            db.add(ay)
            db.flush()
            year_map[year_number] = ay.id

        # Time slots: 5 days, 8 periods/day.
        slot_times = [
            (time(9, 0), time(9, 50)),
            (time(9, 55), time(10, 45)),
            (time(10, 50), time(11, 40)),
            (time(11, 45), time(12, 35)),
            (time(12, 40), time(13, 30)),
            (time(14, 0), time(14, 50)),
            (time(14, 55), time(15, 45)),
            (time(15, 50), time(16, 40)),
        ]
        for day in range(5):
            for idx, (st, et) in enumerate(slot_times):
                db.add(
                    TimeSlot(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        day_of_week=day,
                        slot_index=idx,
                        start_time=st,
                        end_time=et,
                        is_lunch_break=False,
                    )
                )

        # Rooms
        for r in data["rooms"]:
            db.add(
                Room(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    code=str(r["id"]),
                    name=str(r["name"]),
                    room_type=ROOM_TYPE_MAP[str(r["type"]).lower()],
                    capacity=int(r.get("capacity", 60)),
                    is_active=True,
                )
            )

        # Teachers
        teacher_uuid_by_code: dict[str, uuid.UUID] = {}
        for t in data["teachers"]:
            tid = uuid.uuid4()
            teacher_uuid_by_code[str(t["id"])] = tid
            db.add(
                Teacher(
                    id=tid,
                    tenant_id=tenant_id,
                    code=str(t["id"]),
                    full_name=str(t["name"]),
                    max_per_day=6,
                    max_per_week=int(t.get("max_preferred_load", 28)),
                    max_continuous=3,
                    is_active=True,
                )
            )

        # Subjects
        subject_uuid_by_code: dict[str, uuid.UUID] = {}
        for s in data["subjects"]:
            sid = uuid.uuid4()
            subject_uuid_by_code[str(s["id"])] = sid
            academic_year = int(s["academic_year"])
            s_type = str(s["type"]).upper()
            dur = 2 if s_type == "LAB" else 1
            lbs = int(s.get("lab_block_size_slots", 2 if s_type == "LAB" else 1))
            db.add(
                Subject(
                    id=sid,
                    tenant_id=tenant_id,
                    program_id=program.id,
                    academic_year_id=year_map[academic_year],
                    code=str(s["id"]),
                    name=str(s["name"]),
                    subject_type=s_type,
                    sessions_per_week=int(s["sessions_per_week"]),
                    max_per_day=1,
                    duration_slots=dur,
                    lab_block_size_slots=lbs,
                    is_active=True,
                    credits=4 if s_type == "THEORY" else 2,
                )
            )

        # Sections
        section_uuid_by_code: dict[str, uuid.UUID] = {}
        section_year_by_code: dict[str, int] = {}
        for s in data["sections"]:
            sec_id = uuid.uuid4()
            code = str(s["id"])
            section_uuid_by_code[code] = sec_id
            section_year_by_code[code] = int(s["academic_year"])
            db.add(
                Section(
                    id=sec_id,
                    tenant_id=tenant_id,
                    program_id=program.id,
                    academic_year_id=year_map[int(s["academic_year"])],
                    code=code,
                    name=str(s["name"]),
                    strength=int(s.get("strength", 65)),
                    track="CORE",
                    is_active=True,
                    max_daily_slots=8,
                )
            )

        db.flush()

        # Section windows full day over all 8 slots.
        for sec_code, sec_id in section_uuid_by_code.items():
            for day in range(5):
                db.add(
                    SectionTimeWindow(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        section_id=sec_id,
                        day_of_week=day,
                        start_slot_index=0,
                        end_slot_index=7,
                    )
                )

        # Section curriculum -> section_subjects and section_elective_blocks.
        section_block_pairs: set[tuple[str, str]] = set()
        for c in data["section_curriculum"]:
            sec_code = str(c["section_id"])
            sec_id = section_uuid_by_code[sec_code]

            for subj_code in c.get("core_subjects", []):
                db.add(
                    SectionSubject(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        section_id=sec_id,
                        subject_id=subject_uuid_by_code[str(subj_code)],
                    )
                )

            for eb in c.get("elective_blocks", []):
                subj_code = str(eb["chosen_subject"])
                db.add(
                    SectionSubject(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        section_id=sec_id,
                        subject_id=subject_uuid_by_code[subj_code],
                    )
                )
                section_block_pairs.add((sec_code, str(eb["block_id"])))

        # Teacher-subject-section mappings from generated assignments.
        seen_tss: set[tuple[str, str, str]] = set()
        for a in data["section_teacher_assignments"]:
            sec_code = str(a["section_id"])
            subj_code = str(a["subject_id"])
            tea_code = str(a["teacher_id"])
            k = (sec_code, subj_code, tea_code)
            if k in seen_tss:
                continue
            seen_tss.add(k)
            db.add(
                TeacherSubjectSection(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    teacher_id=teacher_uuid_by_code[tea_code],
                    subject_id=subject_uuid_by_code[subj_code],
                    section_id=section_uuid_by_code[sec_code],
                    is_active=True,
                )
            )

        # Elective blocks + subjects + section mappings.
        block_uuid_by_code: dict[str, uuid.UUID] = {}
        for b in data["elective_blocks"]:
            bid = uuid.uuid4()
            bcode = str(b["block_id"])
            block_uuid_by_code[bcode] = bid
            ay = int(b["academic_year"])
            db.add(
                ElectiveBlock(
                    id=bid,
                    tenant_id=tenant_id,
                    program_id=program.id,
                    academic_year_id=year_map[ay],
                    name=f"Elective Block {bcode}",
                    code=bcode,
                    is_active=True,
                )
            )

        db.flush()

        # Map teacher by subject from assignments.
        teacher_for_subject: dict[str, str] = {}
        for a in data["section_teacher_assignments"]:
            subj_code = str(a["subject_id"])
            tea_code = str(a["teacher_id"])
            teacher_for_subject.setdefault(subj_code, tea_code)

        for b in data["elective_blocks"]:
            bid = block_uuid_by_code[str(b["block_id"])]
            for subj_code in b.get("subjects", []):
                subj_code = str(subj_code)
                tea_code = teacher_for_subject.get(subj_code)
                if tea_code is None:
                    continue
                db.add(
                    ElectiveBlockSubject(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        block_id=bid,
                        subject_id=subject_uuid_by_code[subj_code],
                        teacher_id=teacher_uuid_by_code[tea_code],
                    )
                )

        for sec_code, bcode in section_block_pairs:
            if bcode not in block_uuid_by_code:
                continue
            db.add(
                SectionElectiveBlock(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    section_id=section_uuid_by_code[sec_code],
                    block_id=block_uuid_by_code[bcode],
                )
            )

        # Combined groups.
        for cg in data.get("combined_classes", []):
            subject_code = str(cg["subject_id"])
            teacher_code = str(cg["teacher_id"])
            sections = [str(x) for x in cg.get("sections", [])]
            if subject_code not in subject_uuid_by_code or teacher_code not in teacher_uuid_by_code:
                continue
            if not sections:
                continue
            ay = section_year_by_code[sections[0]]
            group_id = uuid.uuid4()
            db.add(
                CombinedGroup(
                    id=group_id,
                    tenant_id=tenant_id,
                    academic_year_id=year_map[ay],
                    subject_id=subject_uuid_by_code[subject_code],
                    teacher_id=teacher_uuid_by_code[teacher_code],
                    label=str(cg.get("combined_id", "")),
                )
            )
            for sec_code in sections:
                db.add(
                    CombinedGroupSection(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        combined_group_id=group_id,
                        subject_id=subject_uuid_by_code[subject_code],
                        section_id=section_uuid_by_code[sec_code],
                    )
                )

        db.commit()

        print("[OK] Seeded dataset")
        print(f"tenant_id={tenant_id}")
        print(f"username={args.username}")
        print(f"program_code={program_code}")
        print("counts:")

        checks = [
            ("programs", Program),
            ("academic_years", AcademicYear),
            ("rooms", Room),
            ("teachers", Teacher),
            ("subjects", Subject),
            ("sections", Section),
            ("time_slots", TimeSlot),
            ("section_time_windows", SectionTimeWindow),
            ("section_subjects", SectionSubject),
            ("teacher_subject_sections", TeacherSubjectSection),
            ("elective_blocks", ElectiveBlock),
            ("elective_block_subjects", ElectiveBlockSubject),
            ("section_elective_blocks", SectionElectiveBlock),
            ("combined_groups", CombinedGroup),
            ("combined_group_sections", CombinedGroupSection),
        ]
        for name, model in checks:
            cnt = db.execute(select(model).where(model.tenant_id == tenant_id)).scalars().all()
            print(f"  {name}: {len(cnt)}")

        return 0

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
