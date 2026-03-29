from __future__ import annotations

from collections import defaultdict
import os

from sqlalchemy import select

from api.tenant import where_tenant
from core.db import SessionLocal
from models.program import Program
from models.section import Section
from models.timetable_entry import TimetableEntry
from models.timetable_run import TimetableRun
from solver.context import SolverContext
from solver.data_loader import load_all, build_pruned_slots
from solver.pre_solve_locks import apply_pre_solve_locks
from solver.variables import create_variables

RUN_ID = os.environ.get("RUN_ID", "39458343-35f0-4161-b01a-2a7fd343f9a1")
TARGET_BATCH_INDEX = int(os.environ.get("TARGET_BATCH_INDEX", "3"))  # 0-based


def _chunk(values: list, n: int) -> list[list]:
    return [values[i : i + n] for i in range(0, len(values), n)]


def _build_target_context() -> SolverContext:
    with SessionLocal() as db:
        run = db.get(TimetableRun, RUN_ID)
        if run is None:
            raise RuntimeError(f"Run not found: {RUN_ID}")

        params = run.parameters or {}
        program_code = params.get("program_code")
        if not program_code:
            raise RuntimeError("program_code missing in run.parameters")

        q_program = select(Program).where(Program.code == program_code)
        q_program = where_tenant(q_program, Program, run.tenant_id)
        program = db.execute(q_program).scalars().first()
        if program is None:
            raise RuntimeError(f"Program not found by code: {program_code}")

        q_sections = (
            select(Section.id, Section.code, Section.academic_year_id)
            .where(Section.program_id == program.id)
            .where(Section.is_active.is_(True))
        )
        q_sections = where_tenant(q_sections, Section, run.tenant_id)
        section_rows = db.execute(q_sections).all()

        year_to_sections: dict = defaultdict(list)
        section_code: dict = {}
        for section_id, code, year_id in section_rows:
            if year_id is None:
                continue
            year_to_sections[year_id].append(section_id)
            section_code[section_id] = code

        batches: list[tuple] = []
        for year_id in sorted(year_to_sections.keys()):
            section_ids = sorted(year_to_sections[year_id], key=lambda v: str(v))
            if len(section_ids) > 12:
                for sub in _chunk(section_ids, 8):
                    batches.append((year_id, sub))
            else:
                batches.append((year_id, section_ids))

        if TARGET_BATCH_INDEX >= len(batches):
            raise RuntimeError(
                f"TARGET_BATCH_INDEX={TARGET_BATCH_INDEX} out of range; total batches={len(batches)}"
            )

        target_year_id, target_section_ids = batches[TARGET_BATCH_INDEX]

        print("Target batch year:", target_year_id)
        print("Target sections:", [section_code.get(s, str(s)) for s in target_section_ids])

        prior_section_ids: set = set()
        for i in range(TARGET_BATCH_INDEX):
            prior_section_ids.update(batches[i][1])

        teacher_blocked: dict = defaultdict(set)
        q_entries = (
            select(TimetableEntry.teacher_id, TimetableEntry.slot_id, TimetableEntry.section_id)
            .where(TimetableEntry.run_id == run.id)
        )
        q_entries = where_tenant(q_entries, TimetableEntry, run.tenant_id)
        for teacher_id, slot_id, section_id in db.execute(q_entries).all():
            if section_id in prior_section_ids:
                teacher_blocked[teacher_id].add(slot_id)

        print("Blocked teachers from prior batches:", len(teacher_blocked))

        ctx = SolverContext(
            db=db,
            run=run,
            program_id=program.id,
            academic_year_id=target_year_id,
            section_id_subset=set(target_section_ids),
            seed=run.seed,
            max_time_seconds=60,
            enforce_teacher_load_limits=True,
            require_optimal=False,
            tenant_id=run.tenant_id,
        )
        for teacher_id, blocked_slots in teacher_blocked.items():
            if blocked_slots:
                ctx.external_teacher_blocked_slot_ids[teacher_id].update(blocked_slots)

        load_all(ctx)
        apply_pre_solve_locks(ctx)
        build_pruned_slots(ctx)
        create_variables(ctx)

        return ctx


def _append_deficit(deficits: list[tuple], kind: str, key: tuple, needed: int, cap_sum: int, raw_sum: int, day_break: list[tuple]) -> None:
    if cap_sum < needed:
        deficits.append((kind + "_DAILY_CAP", key, needed, cap_sum, raw_sum, day_break))
    elif raw_sum < needed:
        deficits.append((kind + "_RAW", key, needed, cap_sum, raw_sum, day_break))


def main() -> None:
    ctx = _build_target_context()
    deficits: list[tuple] = []

    # Track which start variables can actually take at least one room.
    x_room_ok = {
        (sec_id, subject_id, slot_id)
        for sec_id, subject_id, slot_id, _room_id in ctx.x_room.keys()
    }
    lab_room_ok = {
        (sec_id, subject_id, day, start_idx)
        for sec_id, subject_id, day, start_idx, _room_id in ctx.lab_room.keys()
    }
    combined_room_ok = {
        (group_id, slot_id)
        for group_id, slot_id, _room_id in ctx.combined_room.keys()
    }
    z_room_ok = {
        (block_id, int(batch_idx), slot_id)
        for block_id, batch_idx, slot_id, _room_id in ctx.z_room.keys()
    }

    x_key_by_var_id = {id(var): key for key, var in ctx.x.items()}
    lab_key_by_var_id = {id(var): key for key, var in ctx.lab_start.items()}
    combined_key_by_var_id = {id(var): key for key, var in ctx.combined_x.items()}
    z_key_by_var_id = {id(var): key for key, var in ctx.z.items()}

    # 1) Regular (non-combined) section subjects
    for section in ctx.sections:
        section_code = str(getattr(section, "code", section.id))
        track = str(getattr(section, "track", "CORE") or "CORE")

        for subject_id, sessions_override in ctx.section_required.get(section.id, []):
            subject = ctx.subject_by_id.get(subject_id)
            if subject is None:
                continue
            if ctx.assigned_teacher_by_section_subject.get((section.id, subject_id)) is None:
                continue

            subject_type = str(getattr(subject, "subject_type", "THEORY"))
            sessions = int(ctx.sessions_for(subject_id, track=track, override=sessions_override) or 0)
            if sessions <= 0:
                continue

            # Combined THEORY handled separately.
            if subject_type == "THEORY" and ctx.combined_gid_by_sec_subj.get((section.id, subject_id)) is not None:
                continue

            if subject_type == "LAB":
                locked = int(ctx.locked_lab_sessions_by_sec_subj.get((section.id, subject_id), 0) or 0)
                needed = sessions - locked
                if needed <= 0:
                    continue

                cap_sum = 0
                raw_sum = 0
                room_cap_sum = 0
                room_raw_sum = 0
                day_break: list[tuple] = []
                for day in range(6):
                    day_terms = ctx.lab_starts_by_sec_subj_day.get((section.id, subject_id, day), [])
                    raw = len(day_terms)
                    raw_sum += raw

                    room_raw = 0
                    for term in day_terms:
                        key = lab_key_by_var_id.get(id(term))
                        if key is not None and key in lab_room_ok:
                            room_raw += 1
                    room_raw_sum += room_raw

                    locked_day = int(
                        ctx.locked_lab_sessions_by_sec_subj_day.get((section.id, subject_id, day), 0) or 0
                    )
                    cap = int(ctx.max_per_day_for(subject_id, track=track) - locked_day)
                    capped = max(0, min(raw, cap))
                    cap_sum += capped
                    room_capped = max(0, min(room_raw, cap))
                    room_cap_sum += room_capped
                    day_break.append((day, raw, room_raw, cap, capped, room_capped))

                _append_deficit(deficits, "LAB", (section_code, str(getattr(subject, "code", subject_id))), needed, cap_sum, raw_sum, day_break)
                _append_deficit(deficits, "LAB_ROOM", (section_code, str(getattr(subject, "code", subject_id))), needed, room_cap_sum, room_raw_sum, day_break)
                continue

            # THEORY
            locked = int(ctx.locked_theory_sessions_by_sec_subj.get((section.id, subject_id), 0) or 0)
            needed = sessions - locked
            if needed <= 0:
                continue

            cap_sum = 0
            raw_sum = 0
            room_cap_sum = 0
            room_raw_sum = 0
            day_break = []
            for day in range(6):
                day_terms = ctx.x_by_sec_subj_day.get((section.id, subject_id, day), [])
                raw = len(day_terms)
                raw_sum += raw

                room_raw = 0
                for term in day_terms:
                    key = x_key_by_var_id.get(id(term))
                    if key is not None and key in x_room_ok:
                        room_raw += 1
                room_raw_sum += room_raw

                locked_day = int(
                    ctx.locked_theory_sessions_by_sec_subj_day.get((section.id, subject_id, day), 0) or 0
                )
                cap = int(ctx.max_per_day_for(subject_id, track=track) - locked_day)
                capped = max(0, min(raw, cap))
                cap_sum += capped
                room_capped = max(0, min(room_raw, cap))
                room_cap_sum += room_capped
                day_break.append((day, raw, room_raw, cap, capped, room_capped))

            _append_deficit(deficits, "THEORY", (section_code, str(getattr(subject, "code", subject_id))), needed, cap_sum, raw_sum, day_break)
            _append_deficit(deficits, "THEORY_ROOM", (section_code, str(getattr(subject, "code", subject_id))), needed, room_cap_sum, room_raw_sum, day_break)

    # 2) Combined theory groups
    for group_id, section_ids in ctx.group_sections.items():
        subject_id = ctx.group_subject.get(group_id)
        subject = ctx.subject_by_id.get(subject_id)
        if subject is None:
            continue

        needed = int(ctx.combined_sessions_required.get(group_id, ctx.sessions_for(subject_id) or 0) or 0)
        if needed <= 0:
            continue

        cap_sum = 0
        raw_sum = 0
        room_cap_sum = 0
        room_raw_sum = 0
        day_break = []
        for day in range(6):
            day_terms = ctx.combined_vars_by_gid_day.get((group_id, day), [])
            raw = len(day_terms)
            raw_sum += raw

            room_raw = 0
            for term in day_terms:
                key = combined_key_by_var_id.get(id(term))
                if key is not None and key in combined_room_ok:
                    room_raw += 1
            room_raw_sum += room_raw

            cap = int(ctx.max_per_day_for(subject_id))
            capped = max(0, min(raw, cap))
            cap_sum += capped
            room_capped = max(0, min(room_raw, cap))
            room_cap_sum += room_capped
            day_break.append((day, raw, room_raw, cap, capped, room_capped))

        key = (
            str(getattr(subject, "code", subject_id)),
            [
                str(getattr(ctx.section_by_id.get(section_id), "code", section_id))
                for section_id in section_ids
                if section_id in ctx.section_by_id
            ],
        )
        _append_deficit(deficits, "COMBINED", key, needed, cap_sum, raw_sum, day_break)
        _append_deficit(deficits, "COMBINED_ROOM", key, needed, room_cap_sum, room_raw_sum, day_break)

    # 3) Elective block batches
    for block_id, batches in ctx.elective_batches_by_block.items():
        pairs = ctx.block_subject_pairs_by_block.get(block_id, [])
        subject_objs = [ctx.subject_by_id.get(subject_id) for subject_id, _ in pairs]
        subject_objs = [subj for subj in subject_objs if subj is not None]
        if not subject_objs:
            continue

        sessions_vals = [ctx.sessions_for(subj.id) for subj in subject_objs]
        if not sessions_vals or len(set(sessions_vals)) != 1:
            continue

        sessions = int(sessions_vals[0])
        max_per_day = min(ctx.max_per_day_for(subj.id) for subj in subject_objs)

        for batch_idx, batch_section_ids in enumerate(batches):
            locked = int(ctx.locked_elective_sessions_by_block_batch.get((block_id, int(batch_idx)), 0) or 0)
            needed = sessions - locked
            if needed <= 0:
                continue

            cap_sum = 0
            raw_sum = 0
            room_cap_sum = 0
            room_raw_sum = 0
            day_break = []
            for day in range(6):
                day_terms = ctx.z_by_block_batch_day.get((block_id, int(batch_idx), day), [])
                raw = len(day_terms)
                raw_sum += raw

                room_raw = 0
                for term in day_terms:
                    key = z_key_by_var_id.get(id(term))
                    if key is not None and key in z_room_ok:
                        room_raw += 1
                room_raw_sum += room_raw

                locked_day = int(
                    ctx.locked_elective_sessions_by_block_batch_day.get((block_id, int(batch_idx), day), 0)
                    or 0
                )
                cap = int(max_per_day - locked_day)
                capped = max(0, min(raw, cap))
                cap_sum += capped
                room_capped = max(0, min(room_raw, cap))
                room_cap_sum += room_capped
                day_break.append((day, raw, room_raw, cap, capped, room_capped))

            key = (
                str(block_id),
                int(batch_idx),
                [
                    str(getattr(ctx.section_by_id.get(section_id), "code", section_id))
                    for section_id in batch_section_ids
                    if section_id in ctx.section_by_id
                ],
            )
            _append_deficit(deficits, "ELECTIVE", key, needed, cap_sum, raw_sum, day_break)
            _append_deficit(deficits, "ELECTIVE_ROOM", key, needed, room_cap_sum, room_raw_sum, day_break)

    print("deficit_count:", len(deficits))
    if not deficits:
        print("No raw/capped-domain deficits found.")
        return

    for item in deficits:
        print(item)


if __name__ == "__main__":
    main()
