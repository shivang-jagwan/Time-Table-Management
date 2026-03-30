#!/usr/bin/env python3
"""List and auto-fix missing teacher assignments.

Workflow:
1) Collect all unique (section_id, subject_id) pairs that currently trigger
   MISSING_TEACHER_ASSIGNMENT in global validation per program.
2) Propose a teacher using conservative heuristics.
3) In dry-run mode, print the full list and proposed actions.
4) With --apply, perform updates/inserts for resolvable rows.

This script is tenant-scoped by username.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import and_, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal, table_exists  # noqa: E402
from models import (  # noqa: E402
    CombinedGroup,
    CombinedGroupSection,
    Program,
    Section,
    Subject,
    Teacher,
    TeacherSubjectSection,
    User,
)
from services.solver_validation import validate_prereqs  # noqa: E402


class _TransientRun:
    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id


@dataclass
class MissingItem:
    program_id: uuid.UUID
    program_code: str
    section_id: uuid.UUID
    section_code: str
    section_year_id: uuid.UUID | None
    subject_id: uuid.UUID
    subject_code: str


@dataclass
class Resolution:
    teacher_id: uuid.UUID | None
    teacher_code: str | None
    teacher_name: str | None
    source: str | None
    action: str | None  # REACTIVATE | INSERT | SKIP
    note: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shivang123", help="Username used to resolve tenant")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (default is dry-run)")
    parser.add_argument(
        "--out",
        default="backend/outputs/missing_teacher_assignments_all.txt",
        help="Output file for full list (workspace-relative or absolute)",
    )
    return parser.parse_args()


def _resolve_out_path(arg_out: str) -> str:
    if os.path.isabs(arg_out):
        return arg_out
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.normpath(os.path.join(root, arg_out))


def _collect_missing_items(db, tenant_id) -> list[MissingItem]:
    programs = (
        db.execute(select(Program).where(Program.tenant_id == tenant_id).order_by(Program.code.asc()))
        .scalars()
        .all()
    )

    missing_map: dict[tuple[uuid.UUID, uuid.UUID], MissingItem] = {}

    for program in programs:
        sections = (
            db.execute(
                select(Section).where(
                    and_(
                        Section.tenant_id == tenant_id,
                        Section.program_id == program.id,
                        Section.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not sections:
            continue

        section_by_id = {s.id: s for s in sections}
        subject_ids: set[uuid.UUID] = set()

        conflicts = validate_prereqs(
            db,
            run=_TransientRun(tenant_id),
            program_id=program.id,
            academic_year_id=None,
            sections=sections,
        )
        # validate_prereqs may stage conflict rows tied to a transient run id.
        # Clear those staged writes; this helper is read-only by design.
        db.rollback()
        for c in conflicts:
            if str(getattr(c, "conflict_type", "")) != "MISSING_TEACHER_ASSIGNMENT":
                continue
            sec_id = getattr(c, "section_id", None)
            subj_id = getattr(c, "subject_id", None)
            if sec_id is None or subj_id is None:
                continue
            subject_ids.add(subj_id)

        if not subject_ids:
            continue

        subject_rows = (
            db.execute(
                select(Subject.id, Subject.code)
                .where(Subject.id.in_(list(subject_ids)))
                .where(Subject.tenant_id == tenant_id)
            )
            .all()
        )
        subject_code_by_id = {sid: str(code or "") for sid, code in subject_rows}

        for c in conflicts:
            if str(getattr(c, "conflict_type", "")) != "MISSING_TEACHER_ASSIGNMENT":
                continue
            sec_id = getattr(c, "section_id", None)
            subj_id = getattr(c, "subject_id", None)
            if sec_id is None or subj_id is None:
                continue

            sec = section_by_id.get(sec_id)
            if sec is None:
                continue

            key = (sec_id, subj_id)
            if key in missing_map:
                continue

            missing_map[key] = MissingItem(
                program_id=program.id,
                program_code=str(getattr(program, "code", "") or ""),
                section_id=sec_id,
                section_code=str(getattr(sec, "code", "") or ""),
                section_year_id=getattr(sec, "academic_year_id", None),
                subject_id=subj_id,
                subject_code=subject_code_by_id.get(subj_id, ""),
            )

    return sorted(
        list(missing_map.values()),
        key=lambda x: (x.program_code, x.section_code, x.subject_code, str(x.section_id), str(x.subject_id)),
    )


def _build_teacher_maps(db, tenant_id):
    teacher_rows = (
        db.execute(
            select(Teacher.id, Teacher.code, Teacher.full_name)
            .where(Teacher.tenant_id == tenant_id)
            .where(Teacher.is_active.is_(True))
        )
        .all()
    )
    teacher_meta = {
        tid: {"code": str(code or ""), "name": str(name or "")}
        for tid, code, name in teacher_rows
    }

    all_tss = (
        db.execute(
            select(
                TeacherSubjectSection.id,
                TeacherSubjectSection.teacher_id,
                TeacherSubjectSection.subject_id,
                TeacherSubjectSection.section_id,
                TeacherSubjectSection.is_active,
            ).where(TeacherSubjectSection.tenant_id == tenant_id)
        )
        .all()
    )

    rows_by_pair: dict[tuple[uuid.UUID, uuid.UUID], list[dict]] = defaultdict(list)
    active_teachers_by_subject: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)

    for rid, tid, subj_id, sec_id, is_active in all_tss:
        rows_by_pair[(sec_id, subj_id)].append(
            {
                "id": rid,
                "teacher_id": tid,
                "subject_id": subj_id,
                "section_id": sec_id,
                "is_active": bool(is_active),
            }
        )
        if bool(is_active):
            active_teachers_by_subject[subj_id].add(tid)

    return teacher_meta, rows_by_pair, active_teachers_by_subject


def _build_program_year_subject_active_teacher_map(db, tenant_id):
    rows = (
        db.execute(
            select(
                Section.program_id,
                Section.academic_year_id,
                TeacherSubjectSection.subject_id,
                TeacherSubjectSection.teacher_id,
            )
            .join(Section, Section.id == TeacherSubjectSection.section_id)
            .where(TeacherSubjectSection.tenant_id == tenant_id)
            .where(Section.tenant_id == tenant_id)
            .where(Section.is_active.is_(True))
            .where(TeacherSubjectSection.is_active.is_(True))
        )
        .all()
    )
    mapping: dict[tuple[uuid.UUID, uuid.UUID | None, uuid.UUID], set[uuid.UUID]] = defaultdict(set)
    for pid, yid, sid, tid in rows:
        mapping[(pid, yid, sid)].add(tid)
    return mapping


def _build_combined_teacher_map(db, tenant_id):
    result: dict[tuple[uuid.UUID, uuid.UUID], set[uuid.UUID]] = defaultdict(set)

    if not (table_exists(db, "combined_groups") and table_exists(db, "combined_group_sections")):
        return result

    rows = (
        db.execute(
            select(
                CombinedGroupSection.section_id,
                CombinedGroup.subject_id,
                CombinedGroup.teacher_id,
            )
            .join(CombinedGroup, CombinedGroup.id == CombinedGroupSection.combined_group_id)
            .where(CombinedGroup.tenant_id == tenant_id)
            .where(CombinedGroupSection.tenant_id == tenant_id)
        )
        .all()
    )

    for sec_id, subj_id, teacher_id in rows:
        if teacher_id is None:
            continue
        result[(sec_id, subj_id)].add(teacher_id)

    return result


def _pick_resolution(
    item: MissingItem,
    *,
    rows_by_pair,
    teacher_meta,
    combined_teachers_by_pair,
    active_teachers_by_subject,
    active_teachers_by_prog_year_subject,
) -> Resolution:
    pair = (item.section_id, item.subject_id)
    pair_rows = rows_by_pair.get(pair, [])

    # 1) Exact pair has inactive rows with exactly one unique teacher -> reactivate.
    pair_teacher_ids = {r["teacher_id"] for r in pair_rows}
    pair_active = [r for r in pair_rows if r["is_active"]]
    if not pair_active and len(pair_teacher_ids) == 1:
        teacher_id = next(iter(pair_teacher_ids))
        tmeta = teacher_meta.get(teacher_id, {})
        return Resolution(
            teacher_id=teacher_id,
            teacher_code=tmeta.get("code"),
            teacher_name=tmeta.get("name"),
            source="exact_pair_inactive",
            action="REACTIVATE",
            note="Found exactly one existing inactive teacher mapping for this section+subject.",
        )

    # 2) Combined-group teacher for this exact section+subject if unique.
    cg_teachers = combined_teachers_by_pair.get(pair, set())
    if len(cg_teachers) == 1:
        teacher_id = next(iter(cg_teachers))
        tmeta = teacher_meta.get(teacher_id, {})
        return Resolution(
            teacher_id=teacher_id,
            teacher_code=tmeta.get("code"),
            teacher_name=tmeta.get("name"),
            source="combined_group_teacher",
            action="INSERT",
            note="Using unique teacher configured on combined group for this section+subject.",
        )

    # 3) Unique active teacher for same program+year+subject.
    py_key = (item.program_id, item.section_year_id, item.subject_id)
    py_teachers = active_teachers_by_prog_year_subject.get(py_key, set())
    if len(py_teachers) == 1:
        teacher_id = next(iter(py_teachers))
        tmeta = teacher_meta.get(teacher_id, {})
        return Resolution(
            teacher_id=teacher_id,
            teacher_code=tmeta.get("code"),
            teacher_name=tmeta.get("name"),
            source="program_year_subject_unique",
            action="INSERT",
            note="Using the only active teacher seen for this program+year+subject.",
        )

    # 4) Unique active teacher for subject globally in tenant.
    subj_teachers = active_teachers_by_subject.get(item.subject_id, set())
    if len(subj_teachers) == 1:
        teacher_id = next(iter(subj_teachers))
        tmeta = teacher_meta.get(teacher_id, {})
        return Resolution(
            teacher_id=teacher_id,
            teacher_code=tmeta.get("code"),
            teacher_name=tmeta.get("name"),
            source="subject_unique_global",
            action="INSERT",
            note="Using the only active teacher seen for this subject in tenant.",
        )

    if pair_active:
        # Defensive branch: should not happen if conflict truly says missing, but keep safe.
        return Resolution(
            teacher_id=None,
            teacher_code=None,
            teacher_name=None,
            source=None,
            action="SKIP",
            note="Pair already has an active teacher row; skipped.",
        )

    return Resolution(
        teacher_id=None,
        teacher_code=None,
        teacher_name=None,
        source=None,
        action="SKIP",
        note="No unique safe teacher candidate found.",
    )


def main() -> int:
    args = _parse_args()
    out_path = _resolve_out_path(args.out)

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if user is None:
            print(f"[ERROR] user not found: {args.username}")
            return 1
        tenant_id = user.tenant_id
        if tenant_id is None:
            print("[ERROR] user has no tenant_id")
            return 1

        missing_items = _collect_missing_items(db, tenant_id)

        teacher_meta, rows_by_pair, active_teachers_by_subject = _build_teacher_maps(db, tenant_id)
        active_teachers_by_prog_year_subject = _build_program_year_subject_active_teacher_map(db, tenant_id)
        combined_teachers_by_pair = _build_combined_teacher_map(db, tenant_id)

        lines: list[str] = []
        lines.append("=" * 96)
        lines.append("MISSING TEACHER ASSIGNMENTS (UNIQUE SECTION+SUBJECT)")
        lines.append("=" * 96)
        lines.append(f"tenant_id={tenant_id}")
        lines.append(f"total_missing_unique={len(missing_items)}")
        lines.append("")

        resolutions: dict[tuple[uuid.UUID, uuid.UUID], Resolution] = {}
        can_fix = 0
        cannot_fix = 0

        for idx, item in enumerate(missing_items, start=1):
            res = _pick_resolution(
                item,
                rows_by_pair=rows_by_pair,
                teacher_meta=teacher_meta,
                combined_teachers_by_pair=combined_teachers_by_pair,
                active_teachers_by_subject=active_teachers_by_subject,
                active_teachers_by_prog_year_subject=active_teachers_by_prog_year_subject,
            )
            resolutions[(item.section_id, item.subject_id)] = res

            if res.action in {"REACTIVATE", "INSERT"} and res.teacher_id is not None:
                can_fix += 1
            else:
                cannot_fix += 1

            teacher_desc = "-"
            if res.teacher_id is not None:
                tcode = res.teacher_code or ""
                tname = res.teacher_name or ""
                teacher_desc = f"{res.teacher_id} [{tcode}] {tname}".strip()

            lines.append(
                f"{idx:03d}. program={item.program_code} section={item.section_code} section_id={item.section_id} "
                f"subject={item.subject_code} subject_id={item.subject_id} "
                f"| action={res.action or '-'} source={res.source or '-'} | teacher={teacher_desc} | note={res.note}"
            )

        lines.append("")
        lines.append("SUMMARY")
        lines.append(f"fixable={can_fix}")
        lines.append(f"unresolved={cannot_fix}")
        lines.append(f"mode={'APPLY' if args.apply else 'DRY_RUN'}")

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        print("\n".join(lines[: min(len(lines), 120)]))
        if len(lines) > 120:
            print("...")
            print(f"[INFO] full list written to: {out_path}")

        if not args.apply:
            print("[DRY RUN] no database changes applied")
            return 0

        applied_reactivate = 0
        applied_insert = 0

        for item in missing_items:
            pair = (item.section_id, item.subject_id)
            res = resolutions[pair]
            if res.teacher_id is None or res.action not in {"REACTIVATE", "INSERT"}:
                continue

            pair_rows = rows_by_pair.get(pair, [])

            if res.action == "REACTIVATE":
                activated = False
                for row in pair_rows:
                    if row["teacher_id"] == res.teacher_id:
                        tss_row = db.execute(
                            select(TeacherSubjectSection).where(TeacherSubjectSection.id == row["id"])
                        ).scalar_one_or_none()
                        if tss_row is not None and not bool(tss_row.is_active):
                            tss_row.is_active = True
                            activated = True
                            break
                if activated:
                    applied_reactivate += 1
                continue

            # INSERT branch.
            # If row for same teacher already exists inactive, flip it active instead of creating duplicate.
            existing_same_teacher = None
            for row in pair_rows:
                if row["teacher_id"] == res.teacher_id:
                    existing_same_teacher = row
                    break

            if existing_same_teacher is not None:
                tss_row = db.execute(
                    select(TeacherSubjectSection).where(TeacherSubjectSection.id == existing_same_teacher["id"])
                ).scalar_one_or_none()
                if tss_row is not None and not bool(tss_row.is_active):
                    tss_row.is_active = True
                    applied_reactivate += 1
            else:
                db.add(
                    TeacherSubjectSection(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        teacher_id=res.teacher_id,
                        subject_id=item.subject_id,
                        section_id=item.section_id,
                        is_active=True,
                    )
                )
                applied_insert += 1

        db.commit()
        print(
            f"[OK] applied fixes: reactivated={applied_reactivate}, inserted={applied_insert}, total={applied_reactivate + applied_insert}"
        )
        return 0

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
