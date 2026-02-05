from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Any, Iterable


class DiagnosticType(str, Enum):
    TEACHER_LOAD_EXCEEDS_LIMIT = "TEACHER_LOAD_EXCEEDS_LIMIT"
    TEACHER_DAILY_LOAD_VIOLATION = "TEACHER_DAILY_LOAD_VIOLATION"
    TEACHER_OFFDAY_CONFLICT = "TEACHER_OFFDAY_CONFLICT"
    SECTION_SLOT_DEFICIT = "SECTION_SLOT_DEFICIT"
    LAB_BLOCK_UNFIT = "LAB_BLOCK_UNFIT"
    SPECIAL_ALLOTMENT_DEADLOCK = "SPECIAL_ALLOTMENT_DEADLOCK"
    LOCKED_SESSIONS_EXCEED_REQUIREMENT = "LOCKED_SESSIONS_EXCEED_REQUIREMENT"
    ROOM_CAPACITY_SHORTAGE = "ROOM_CAPACITY_SHORTAGE"
    SPECIAL_ROOM_MISUSE = "SPECIAL_ROOM_MISUSE"
    COMBINED_GROUP_NO_INTERSECTION = "COMBINED_GROUP_NO_INTERSECTION"
    DIAGNOSTICS_INCONCLUSIVE = "DIAGNOSTICS_INCONCLUSIVE"


def summarize_diagnostics(diagnostics: list[dict[str, Any]]) -> str:
    n = len(diagnostics)
    if n <= 0:
        return "No blocking conflicts detected by diagnostics checks."
    if n == 1:
        return "1 blocking conflict detected."
    return f"{n} blocking conflicts detected."


def _day_name(day: int) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    return names[day] if 0 <= day < len(names) else str(day)


def _diag(*, dtype: DiagnosticType, explanation: str, **payload: Any) -> dict[str, Any]:
    return {"type": dtype.value, **payload, "explanation": explanation}


def _slots_for_subject(subj: Any, sessions_per_week: int) -> int:
    # Solver teacher load is counted per occupied *slot*.
    if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
        block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
        if block < 1:
            block = 1
        return int(sessions_per_week) * int(block)
    return int(sessions_per_week)


def _derive_block_sessions_per_week(block_pairs: list[tuple[Any, Any]], subject_by_id: dict[Any, Any]) -> int | None:
    subj_objs = [subject_by_id.get(subj_id) for subj_id, _tid in block_pairs]
    subj_objs = [s for s in subj_objs if s is not None]
    if len(subj_objs) != len(block_pairs):
        return None
    if any(str(getattr(s, "subject_type", "THEORY")) != "THEORY" for s in subj_objs):
        return None
    sessions_vals = [int(getattr(s, "sessions_per_week", 0) or 0) for s in subj_objs]
    if not sessions_vals or len(set(sessions_vals)) != 1:
        return None
    v = int(sessions_vals[0])
    return v if v > 0 else None


def run_infeasibility_analysis(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pre-solve diagnostic checks (no CP-SAT inspection).

    This is intentionally "best effort": it detects common *deterministic* impossibilities
    and produces human-actionable explanations.

    Expected keys in `data` (all optional, but results improve with more context):
    - sections, section_required, subjects_by_id, teachers_by_id
    - assigned_teacher_by_section_subject
    - slots, slot_by_day_index, slot_info
    - windows_by_section
    - fixed_entries, special_allotments
    - group_sections, group_subject
    - block_subject_pairs_by_block, blocks_by_section
    - room_by_id, rooms_by_type
    """

    diagnostics: list[dict[str, Any]] = []

    sections: list[Any] = list(data.get("sections") or [])
    section_by_id = {s.id: s for s in sections if getattr(s, "id", None) is not None}

    subject_by_id: dict[Any, Any] = dict(data.get("subject_by_id") or data.get("subjects_by_id") or {})
    teacher_by_id: dict[Any, Any] = dict(data.get("teacher_by_id") or data.get("teachers_by_id") or {})
    room_by_id: dict[Any, Any] = dict(data.get("room_by_id") or {})

    section_required: dict[Any, list[tuple[Any, int | None]]] = dict(data.get("section_required") or {})
    assigned_teacher_by_section_subject: dict[tuple[Any, Any], Any] = dict(data.get("assigned_teacher_by_section_subject") or {})

    slots: list[Any] = list(data.get("slots") or [])
    slot_info: dict[Any, tuple[int, int]] = dict(data.get("slot_info") or {})
    slot_by_day_index: dict[tuple[int, int], Any] = dict(data.get("slot_by_day_index") or {})

    windows_by_section = data.get("windows_by_section") or {}
    fixed_entries: list[Any] = list(data.get("fixed_entries") or [])
    special_allotments: list[Any] = list(data.get("special_allotments") or [])

    group_sections: dict[Any, list[Any]] = dict(data.get("group_sections") or {})
    group_subject: dict[Any, Any] = dict(data.get("group_subject") or {})

    blocks_by_section: dict[Any, list[Any]] = dict(data.get("blocks_by_section") or {})
    block_subject_pairs_by_block: dict[Any, list[tuple[Any, Any]]] = dict(data.get("block_subject_pairs_by_block") or {})

    rooms_by_type = data.get("rooms_by_type") or {}

    # ------------------------
    # Helpers: section windows
    # ------------------------
    window_slot_ids_by_section: dict[Any, set[Any]] = defaultdict(set)
    window_slot_indices_by_section_day: dict[tuple[Any, int], list[int]] = defaultdict(list)

    # Support both: dict[sec_id] -> [SectionTimeWindow] and list[SectionTimeWindow].
    if isinstance(windows_by_section, dict):
        for sec_id, wins in windows_by_section.items():
            for w in wins or []:
                day = int(getattr(w, "day_of_week", 0))
                start = int(getattr(w, "start_slot_index", 0))
                end = int(getattr(w, "end_slot_index", -1))
                for si in range(start, end + 1):
                    ts = slot_by_day_index.get((day, si))
                    if ts is None:
                        continue
                    window_slot_ids_by_section[sec_id].add(ts.id)
                    window_slot_indices_by_section_day[(sec_id, day)].append(int(si))
    else:
        for w in windows_by_section or []:
            sec_id = getattr(w, "section_id", None)
            if sec_id is None:
                continue
            day = int(getattr(w, "day_of_week", 0))
            start = int(getattr(w, "start_slot_index", 0))
            end = int(getattr(w, "end_slot_index", -1))
            for si in range(start, end + 1):
                ts = slot_by_day_index.get((day, si))
                if ts is None:
                    continue
                window_slot_ids_by_section[sec_id].add(ts.id)
                window_slot_indices_by_section_day[(sec_id, day)].append(int(si))

    for key in list(window_slot_indices_by_section_day.keys()):
        window_slot_indices_by_section_day[key] = sorted(set(window_slot_indices_by_section_day[key]))

    active_days = sorted({int(getattr(s, "day_of_week", 0)) for s in slots})

    # ------------------------
    # Compute "locked" indices
    # ------------------------
    locked_slot_indices_by_section_day: dict[tuple[Any, int], set[int]] = defaultdict(set)
    locked_slots_by_teacher_day: dict[tuple[Any, int], int] = defaultdict(int)

    def _add_locked(*, sec_id: Any, teacher_id: Any, slot_id: Any, source: str, subject_id: Any | None = None) -> None:
        di = slot_info.get(slot_id)
        if not di:
            return
        day, slot_idx = int(di[0]), int(di[1])
        locked_slot_indices_by_section_day[(sec_id, day)].add(int(slot_idx))
        locked_slots_by_teacher_day[(teacher_id, day)] += 1

    # Fixed entries lock a single slot for THEORY, multiple slots for LAB.
    for fe in fixed_entries:
        subj = subject_by_id.get(getattr(fe, "subject_id", None))
        if subj is None:
            continue
        slot_id = getattr(fe, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        day, slot_idx = int(di[0]), int(di[1])
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
            block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1
            for j in range(block):
                ts = slot_by_day_index.get((day, slot_idx + j))
                if ts is None:
                    continue
                _add_locked(
                    sec_id=getattr(fe, "section_id", None),
                    teacher_id=getattr(fe, "teacher_id", None),
                    slot_id=ts.id,
                    source="FIXED_ENTRY",
                    subject_id=getattr(fe, "subject_id", None),
                )
        else:
            _add_locked(
                sec_id=getattr(fe, "section_id", None),
                teacher_id=getattr(fe, "teacher_id", None),
                slot_id=slot_id,
                source="FIXED_ENTRY",
                subject_id=getattr(fe, "subject_id", None),
            )

    # Special allotments lock similarly.
    for sa in special_allotments:
        subj = subject_by_id.get(getattr(sa, "subject_id", None))
        if subj is None:
            continue
        slot_id = getattr(sa, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        day, slot_idx = int(di[0]), int(di[1])
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
            block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1
            for j in range(block):
                ts = slot_by_day_index.get((day, slot_idx + j))
                if ts is None:
                    continue
                _add_locked(
                    sec_id=getattr(sa, "section_id", None),
                    teacher_id=getattr(sa, "teacher_id", None),
                    slot_id=ts.id,
                    source="SPECIAL_ALLOTMENT",
                    subject_id=getattr(sa, "subject_id", None),
                )
        else:
            _add_locked(
                sec_id=getattr(sa, "section_id", None),
                teacher_id=getattr(sa, "teacher_id", None),
                slot_id=slot_id,
                source="SPECIAL_ALLOTMENT",
                subject_id=getattr(sa, "subject_id", None),
            )

    # ------------------------
    # A) Teacher weekly load
    # ------------------------
    teacher_required_slots: dict[Any, int] = defaultdict(int)
    teacher_contrib: dict[Any, list[dict[str, Any]]] = defaultdict(list)

    # Combined groups: count once per group for the shared teacher.
    counted_combined_groups: set[Any] = set()
    for gid, sec_ids in group_sections.items():
        subj_id = group_subject.get(gid)
        if subj_id is None:
            continue
        subj = subject_by_id.get(subj_id)
        if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
            continue
        if gid in counted_combined_groups:
            continue

        # Determine a single assigned teacher (must match across sections).
        assigned_tid = None
        for sid in sec_ids:
            tid = assigned_teacher_by_section_subject.get((sid, subj_id))
            if tid is None:
                assigned_tid = None
                break
            if assigned_tid is None:
                assigned_tid = tid
            elif assigned_tid != tid:
                assigned_tid = None
        # If we have a consistent teacher across the combined group, attribute once.
        if assigned_tid is None:
            continue
        sessions_per_week = int(getattr(subj, "sessions_per_week", 0) or 0)
        if sessions_per_week <= 0:
            continue
        teacher_required_slots[assigned_tid] += int(sessions_per_week)
        teacher_contrib[assigned_tid].append(
            {
                "source": "COMBINED_GROUP",
                "group_id": str(gid),
                "subject_code": getattr(subj, "code", None),
                "sections": [getattr(section_by_id.get(sid), "code", str(sid)) for sid in sec_ids],
                "slots": int(sessions_per_week),
            }
        )
        counted_combined_groups.add(gid)
    # ------------------------
    # A0) Locked sessions exceed demand
    # ------------------------
    # If fixed entries / special allotments already exceed required sessions_per_week or max_per_day,
    # the solver will intentionally force infeasible (needed < 0 / cap < 0).
    locked_theory_by_sec_subj = defaultdict(int)  # (sec_id, subj_id) -> count
    locked_theory_by_sec_subj_day = defaultdict(int)  # (sec_id, subj_id, day) -> count
    locked_lab_blocks_by_sec_subj = defaultdict(int)  # (sec_id, subj_id) -> blocks
    locked_lab_blocks_by_sec_subj_day = defaultdict(int)  # (sec_id, subj_id, day) -> blocks

    def _inc_locked(sec_id: Any, subj_id: Any, day: int, *, is_lab: bool) -> None:
        if sec_id is None or subj_id is None:
            return
        if is_lab:
            locked_lab_blocks_by_sec_subj[(sec_id, subj_id)] += 1
            locked_lab_blocks_by_sec_subj_day[(sec_id, subj_id, int(day))] += 1
        else:
            locked_theory_by_sec_subj[(sec_id, subj_id)] += 1
            locked_theory_by_sec_subj_day[(sec_id, subj_id, int(day))] += 1

    # Fixed entries
    for fe in fixed_entries:
        subj_id = getattr(fe, "subject_id", None)
        subj = subject_by_id.get(subj_id)
        if subj is None:
            continue
        slot_id = getattr(fe, "slot_id", None)
        di = slot_info.get(slot_id)
        if not di:
            continue
        day = int(di[0])
        is_lab = str(getattr(subj, "subject_type", "THEORY")) == "LAB"
        _inc_locked(getattr(fe, "section_id", None), subj_id, day, is_lab=is_lab)

    # Special allotments
    for sa in special_allotments:
        subj_id = getattr(sa, "subject_id", None)
        subj = subject_by_id.get(subj_id)
        if subj is None:
            continue
        slot_id = getattr(sa, "slot_id", None)
        di = slot_info.get(slot_id)
        if not di:
            continue
        day = int(di[0])
        is_lab = str(getattr(subj, "subject_type", "THEORY")) == "LAB"
        _inc_locked(getattr(sa, "section_id", None), subj_id, day, is_lab=is_lab)

    for sec_id, reqs in section_required.items():
        sec = section_by_id.get(sec_id)
        for subj_id, sessions_override in reqs or []:
            subj = subject_by_id.get(subj_id)
            if subj is None:
                continue
            sessions_per_week = int(
                sessions_override if sessions_override is not None else getattr(subj, "sessions_per_week", 0) or 0
            )
            if sessions_per_week <= 0:
                continue

            if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
                locked_blocks = int(locked_lab_blocks_by_sec_subj.get((sec_id, subj_id), 0) or 0)
                if locked_blocks > sessions_per_week:
                    diagnostics.append(
                        _diag(
                            dtype=DiagnosticType.LOCKED_SESSIONS_EXCEED_REQUIREMENT,
                            section_id=str(sec_id),
                            section=getattr(sec, "code", None),
                            subject_id=str(subj_id),
                            subject=getattr(subj, "code", None),
                            locked_sessions=int(locked_blocks),
                            required_sessions=int(sessions_per_week),
                            explanation=(
                                f"Subject {getattr(subj, 'code', subj_id)} in section {getattr(sec, 'code', sec_id)} "
                                f"has {int(locked_blocks)} locked LAB blocks, but only {int(sessions_per_week)} are required per week."
                            ),
                        )
                    )
                max_per_day = int(getattr(subj, "max_per_day", 1) or 1)
                for day in active_days:
                    locked_day = int(locked_lab_blocks_by_sec_subj_day.get((sec_id, subj_id, int(day)), 0) or 0)
                    if locked_day > max_per_day:
                        diagnostics.append(
                            _diag(
                                dtype=DiagnosticType.LOCKED_SESSIONS_EXCEED_REQUIREMENT,
                                section_id=str(sec_id),
                                section=getattr(sec, "code", None),
                                subject_id=str(subj_id),
                                subject=getattr(subj, "code", None),
                                day=int(day),
                                locked_sessions=int(locked_day),
                                max_per_day=int(max_per_day),
                                explanation=(
                                    f"Subject {getattr(subj, 'code', subj_id)} in section {getattr(sec, 'code', sec_id)} "
                                    f"has {int(locked_day)} locked LAB blocks on {_day_name(int(day))}, exceeding max_per_day={int(max_per_day)}."
                                ),
                            )
                        )
                continue

            locked = int(locked_theory_by_sec_subj.get((sec_id, subj_id), 0) or 0)
            if locked > sessions_per_week:
                diagnostics.append(
                    _diag(
                        dtype=DiagnosticType.LOCKED_SESSIONS_EXCEED_REQUIREMENT,
                        section_id=str(sec_id),
                        section=getattr(sec, "code", None),
                        subject_id=str(subj_id),
                        subject=getattr(subj, "code", None),
                        locked_sessions=int(locked),
                        required_sessions=int(sessions_per_week),
                        explanation=(
                            f"Subject {getattr(subj, 'code', subj_id)} in section {getattr(sec, 'code', sec_id)} "
                            f"has {int(locked)} locked THEORY sessions, but only {int(sessions_per_week)} are required per week."
                        ),
                    )
                )
            max_per_day = int(getattr(subj, "max_per_day", 1) or 1)
            for day in active_days:
                locked_day = int(locked_theory_by_sec_subj_day.get((sec_id, subj_id, int(day)), 0) or 0)
                if locked_day > max_per_day:
                    diagnostics.append(
                        _diag(
                            dtype=DiagnosticType.LOCKED_SESSIONS_EXCEED_REQUIREMENT,
                            section_id=str(sec_id),
                            section=getattr(sec, "code", None),
                            subject_id=str(subj_id),
                            subject=getattr(subj, "code", None),
                            day=int(day),
                            locked_sessions=int(locked_day),
                            max_per_day=int(max_per_day),
                            explanation=(
                                f"Subject {getattr(subj, 'code', subj_id)} in section {getattr(sec, 'code', sec_id)} "
                                f"has {int(locked_day)} locked THEORY sessions on {_day_name(int(day))}, exceeding max_per_day={int(max_per_day)}."
                            ),
                        )
                    )
                

    # Per-section subjects (excluding combined theory which is counted above).
    for sec_id, reqs in section_required.items():
        sec = section_by_id.get(sec_id)
        for subj_id, sessions_override in reqs or []:
            subj = subject_by_id.get(subj_id)
            if subj is None:
                continue
            # Skip THEORY subjects that are part of a combined group to avoid double-counting.
            skip_section_subject = False
            if str(getattr(subj, "subject_type", "THEORY")) == "THEORY":
                for gid, g_subj in group_subject.items():
                    if g_subj == subj_id and sec_id in group_sections.get(gid, []):
                        skip_section_subject = True
                        break
            if skip_section_subject:
                continue
            tid = assigned_teacher_by_section_subject.get((sec_id, subj_id))
            if tid is None:
                continue
            sessions_per_week = int(sessions_override if sessions_override is not None else getattr(subj, "sessions_per_week", 0) or 0)
            if sessions_per_week <= 0:
                continue

            slots_needed = _slots_for_subject(subj, sessions_per_week)
            teacher_required_slots[tid] += int(slots_needed)
            teacher_contrib[tid].append(
                {
                    "source": "SECTION_SUBJECT",
                    "section_code": getattr(sec, "code", None),
                    "subject_code": getattr(subj, "code", None),
                    "subject_type": str(getattr(subj, "subject_type", "")),
                    "slots": int(slots_needed),
                }
            )

    # Elective blocks: each teacher in block occupies each block session.
    for sec_id, block_ids in blocks_by_section.items():
        sec = section_by_id.get(sec_id)
        for block_id in block_ids or []:
            pairs = block_subject_pairs_by_block.get(block_id, [])
            sessions_per_week = _derive_block_sessions_per_week(pairs, subject_by_id)
            if not sessions_per_week:
                continue
            for subj_id, teacher_id in pairs:
                subj = subject_by_id.get(subj_id)
                teacher_required_slots[teacher_id] += int(sessions_per_week)
                teacher_contrib[teacher_id].append(
                    {
                        "source": "ELECTIVE_BLOCK",
                        "section_code": getattr(sec, "code", None),
                        "block_id": str(block_id),
                        "subject_code": getattr(subj, "code", None),
                        "slots": int(sessions_per_week),
                    }
                )

    for teacher_id, required_slots in sorted(teacher_required_slots.items(), key=lambda kv: kv[0]):
        teacher = teacher_by_id.get(teacher_id)
        if teacher is None:
            continue
        max_allowed = int(getattr(teacher, "max_per_week", 0) or 0)
        if int(required_slots) > int(max_allowed):
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.TEACHER_LOAD_EXCEEDS_LIMIT,
                    teacher_id=str(teacher_id),
                    teacher=getattr(teacher, "code", None),
                    required_slots=int(required_slots),
                    max_allowed=int(max_allowed),
                    contributors=teacher_contrib.get(teacher_id, []),
                    explanation=(
                        f"Teacher {getattr(teacher, 'code', teacher_id)} is assigned {int(required_slots)} required slots "
                        f"but max_per_week is {int(max_allowed)}."
                    ),
                )
            )

    # ------------------------
    # B) Teacher daily load
    # ------------------------
    for teacher_id, teacher in teacher_by_id.items():
        max_per_day = int(getattr(teacher, "max_per_day", 0) or 0)
        if max_per_day <= 0:
            continue

        # Locked-only hard violations.
        for day in active_days:
            locked = int(locked_slots_by_teacher_day.get((teacher_id, day), 0) or 0)
            if locked > max_per_day:
                diagnostics.append(
                    _diag(
                        dtype=DiagnosticType.TEACHER_DAILY_LOAD_VIOLATION,
                        teacher_id=str(teacher_id),
                        teacher=getattr(teacher, "code", None),
                        day_of_week=int(day),
                        day_name=_day_name(int(day)),
                        locked_slots=int(locked),
                        max_allowed=int(max_per_day),
                        explanation=(
                            f"Teacher {getattr(teacher, 'code', teacher_id)} has {int(locked)} locked slots on "
                            f"{_day_name(int(day))} but max_per_day is {int(max_per_day)}."
                        ),
                    )
                )

        # Capacity bound across available days.
        available_days = [d for d in active_days if getattr(teacher, "weekly_off_day", None) is None or int(getattr(teacher, "weekly_off_day")) != int(d)]
        if not available_days:
            continue
        required = int(teacher_required_slots.get(teacher_id, 0) or 0)
        if required > int(max_per_day) * len(available_days):
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.TEACHER_DAILY_LOAD_VIOLATION,
                    teacher_id=str(teacher_id),
                    teacher=getattr(teacher, "code", None),
                    required_slots=int(required),
                    max_per_day=int(max_per_day),
                    available_days=len(available_days),
                    explanation=(
                        f"Teacher {getattr(teacher, 'code', teacher_id)} requires {int(required)} slots/week, but daily limit "
                        f"max_per_day={int(max_per_day)} over {len(available_days)} working days caps at {int(max_per_day) * len(available_days)}."
                    ),
                )
            )

    # ------------------------
    # C) Teacher off-day clashes
    # ------------------------
    def _emit_offday_conflict(*, teacher: Any, teacher_id: Any, slot_id: Any, source: str, section_id: Any, subject_id: Any | None) -> None:
        di = slot_info.get(slot_id)
        if not di:
            return
        day, slot_idx = int(di[0]), int(di[1])
        off = getattr(teacher, "weekly_off_day", None)
        diagnostics.append(
            _diag(
                dtype=DiagnosticType.TEACHER_OFFDAY_CONFLICT,
                teacher_id=str(teacher_id),
                teacher=getattr(teacher, "code", None),
                weekly_off_day=int(off) if off is not None else None,
                weekly_off_day_name=_day_name(int(off)) if off is not None else None,
                day_of_week=int(day),
                day_name=_day_name(int(day)),
                slot_index=int(slot_idx),
                source=source,
                section_id=str(section_id) if section_id is not None else None,
                section=getattr(section_by_id.get(section_id), "code", None) if section_id is not None else None,
                subject_id=str(subject_id) if subject_id is not None else None,
                subject=getattr(subject_by_id.get(subject_id), "code", None) if subject_id is not None else None,
                explanation=(
                    f"Teacher {getattr(teacher, 'code', teacher_id)} has weekly off day = {_day_name(int(off))} "
                    f"but {source} is scheduled on {_day_name(int(day))} slot #{int(slot_idx)}."
                ),
            )
        )

    for fe in fixed_entries:
        teacher_id = getattr(fe, "teacher_id", None)
        teacher = teacher_by_id.get(teacher_id)
        if teacher is None:
            continue
        off = getattr(teacher, "weekly_off_day", None)
        if off is None:
            continue
        slot_id = getattr(fe, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        if int(di[0]) == int(off):
            _emit_offday_conflict(
                teacher=teacher,
                teacher_id=teacher_id,
                slot_id=slot_id,
                source="FIXED_ENTRY",
                section_id=getattr(fe, "section_id", None),
                subject_id=getattr(fe, "subject_id", None),
            )

    for sa in special_allotments:
        teacher_id = getattr(sa, "teacher_id", None)
        teacher = teacher_by_id.get(teacher_id)
        if teacher is None:
            continue
        off = getattr(teacher, "weekly_off_day", None)
        if off is None:
            continue
        slot_id = getattr(sa, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        if int(di[0]) == int(off):
            _emit_offday_conflict(
                teacher=teacher,
                teacher_id=teacher_id,
                slot_id=slot_id,
                source="SPECIAL_ALLOTMENT",
                section_id=getattr(sa, "section_id", None),
                subject_id=getattr(sa, "subject_id", None),
            )

    # ------------------------
    # D) Section slot deficit
    # ------------------------
    # Compute per-section total demanded *slot* count.
    section_demand_slots: dict[Any, int] = defaultdict(int)

    # Add base curriculum demand.
    for sec_id, reqs in section_required.items():
        for subj_id, sessions_override in reqs or []:
            subj = subject_by_id.get(subj_id)
            if subj is None:
                continue
            sessions_per_week = int(sessions_override if sessions_override is not None else getattr(subj, "sessions_per_week", 0) or 0)
            if sessions_per_week <= 0:
                continue

            # Combined THEORY is still demand for each section.
            section_demand_slots[sec_id] += int(_slots_for_subject(subj, sessions_per_week))

    # Add elective block demand (1 slot per block session).
    for sec_id, block_ids in blocks_by_section.items():
        for block_id in block_ids or []:
            pairs = block_subject_pairs_by_block.get(block_id, [])
            sessions_per_week = _derive_block_sessions_per_week(pairs, subject_by_id)
            if not sessions_per_week:
                continue
            section_demand_slots[sec_id] += int(sessions_per_week)

    for sec_id, demand in sorted(section_demand_slots.items(), key=lambda kv: kv[0]):
        avail = len(window_slot_ids_by_section.get(sec_id, set()))
        if int(demand) > int(avail):
            sec = section_by_id.get(sec_id)
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.SECTION_SLOT_DEFICIT,
                    section_id=str(sec_id),
                    section=getattr(sec, "code", None),
                    required_slots=int(demand),
                    available_slots=int(avail),
                    explanation=(
                        f"Section {getattr(sec, 'code', sec_id)} requires {int(demand)} slots but only {int(avail)} are available in time windows."
                    ),
                )
            )

    # ------------------------
    # E) Lab block fit failure
    # ------------------------
    def _contiguous_starts(sorted_indices: list[int], block: int) -> Iterable[int]:
        if block <= 1:
            for idx in sorted_indices:
                yield idx
            return
        if not sorted_indices:
            return
        run_start = sorted_indices[0]
        prev = sorted_indices[0]
        for idx in sorted_indices[1:]:
            if idx == prev + 1:
                prev = idx
                continue
            run_end = prev
            if (run_end - run_start + 1) >= block:
                for start in range(run_start, run_end - block + 2):
                    yield start
            run_start = idx
            prev = idx
        run_end = prev
        if (run_end - run_start + 1) >= block:
            for start in range(run_start, run_end - block + 2):
                yield start

    for sec_id, reqs in section_required.items():
        sec = section_by_id.get(sec_id)
        for subj_id, sessions_override in reqs or []:
            subj = subject_by_id.get(subj_id)
            if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "LAB":
                continue
            sessions_per_week = int(sessions_override if sessions_override is not None else getattr(subj, "sessions_per_week", 0) or 0)
            if sessions_per_week <= 0:
                continue

            # Remaining sessions could be 0 if everything is locked via special allotments.
            locked_lab_blocks = 0
            for sa in special_allotments:
                if getattr(sa, "section_id", None) == sec_id and getattr(sa, "subject_id", None) == subj_id:
                    locked_lab_blocks += 1
            remaining = int(sessions_per_week) - int(locked_lab_blocks)
            if remaining <= 0:
                continue

            block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1

            any_fit = False
            for day in active_days:
                indices = list(window_slot_indices_by_section_day.get((sec_id, int(day)), []))
                if not indices or len(indices) < block:
                    continue
                locked = locked_slot_indices_by_section_day.get((sec_id, int(day)), set())
                free_indices = [i for i in indices if i not in locked]
                if len(free_indices) < block:
                    continue
                if any(True for _ in _contiguous_starts(free_indices, block)):
                    any_fit = True
                    break

            if not any_fit:
                diagnostics.append(
                    _diag(
                        dtype=DiagnosticType.LAB_BLOCK_UNFIT,
                        section_id=str(sec_id),
                        section=getattr(sec, "code", None),
                        subject_id=str(subj_id),
                        subject=getattr(subj, "code", None),
                        lab_block_size=int(block),
                        remaining_sessions=int(remaining),
                        explanation=(
                            f"Subject {getattr(subj, 'code', subj_id)} requires {int(block)} contiguous slots, "
                            f"but no {int(block)} consecutive free slots exist for section {getattr(sec, 'code', sec_id)}."
                        ),
                    )
                )

    # ------------------------
    # F) Special allotment deadlock detection (bounds)
    # ------------------------
    # Detect when per-day caps after locked sessions (fixed + special) make remaining sessions impossible.
    locked_theory_by_sec_subj_day: dict[tuple[Any, Any, int], int] = defaultdict(int)
    for fe in fixed_entries:
        subj = subject_by_id.get(getattr(fe, "subject_id", None))
        if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
            continue
        di = slot_info.get(getattr(fe, "slot_id", None))
        if not di:
            continue
        day = int(di[0])
        locked_theory_by_sec_subj_day[(getattr(fe, "section_id", None), getattr(fe, "subject_id", None), day)] += 1

    for sa in special_allotments:
        subj = subject_by_id.get(getattr(sa, "subject_id", None))
        if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
            continue
        di = slot_info.get(getattr(sa, "slot_id", None))
        if not di:
            continue
        day = int(di[0])
        locked_theory_by_sec_subj_day[(getattr(sa, "section_id", None), getattr(sa, "subject_id", None), day)] += 1

    for sec_id, reqs in section_required.items():
        sec = section_by_id.get(sec_id)
        for subj_id, sessions_override in reqs or []:
            subj = subject_by_id.get(subj_id)
            if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
                continue
            sessions_per_week = int(sessions_override if sessions_override is not None else getattr(subj, "sessions_per_week", 0) or 0)
            if sessions_per_week <= 0:
                continue
            locked_total = 0
            for day in active_days:
                locked_total += int(locked_theory_by_sec_subj_day.get((sec_id, subj_id, int(day)), 0) or 0)
            remaining = int(sessions_per_week) - int(locked_total)
            if remaining <= 0:
                continue

            max_per_day = int(getattr(subj, "max_per_day", 1) or 1)
            # Available days for this section in its window.
            sec_days = [d for d in active_days if window_slot_indices_by_section_day.get((sec_id, int(d)), [])]
            # Respect teacher off-day bound too.
            tid = assigned_teacher_by_section_subject.get((sec_id, subj_id))
            teacher = teacher_by_id.get(tid) if tid is not None else None
            if teacher is not None and getattr(teacher, "weekly_off_day", None) is not None:
                sec_days = [d for d in sec_days if int(d) != int(getattr(teacher, "weekly_off_day"))]

            if not sec_days:
                continue

            day_cap_total = 0
            for d in sec_days:
                locked_day = int(locked_theory_by_sec_subj_day.get((sec_id, subj_id, int(d)), 0) or 0)
                cap = int(max_per_day) - int(locked_day)
                if cap > 0:
                    day_cap_total += cap

            if day_cap_total < remaining:
                diagnostics.append(
                    _diag(
                        dtype=DiagnosticType.SPECIAL_ALLOTMENT_DEADLOCK,
                        section_id=str(sec_id),
                        section=getattr(sec, "code", None),
                        subject_id=str(subj_id),
                        subject=getattr(subj, "code", None),
                        required_sessions=int(sessions_per_week),
                        locked_sessions=int(locked_total),
                        remaining_sessions=int(remaining),
                        max_per_day=int(max_per_day),
                        feasible_remaining_capacity=int(day_cap_total),
                        explanation=(
                            f"Special allotments for {getattr(subj, 'code', subj_id)} lock {int(locked_total)}/{int(sessions_per_week)} sessions. "
                            f"With max_per_day={int(max_per_day)}, remaining capacity ({int(day_cap_total)}) is insufficient for remaining {int(remaining)} sessions."
                        ),
                    )
                )

    # ------------------------
    # G) Room shortage (locked-only)
    # ------------------------
    theory_room_capacity = len(rooms_by_type.get("CLASSROOM", []) or []) + len(rooms_by_type.get("LT", []) or [])
    lab_room_capacity = len(rooms_by_type.get("LAB", []) or [])

    locked_theory_by_slot: dict[Any, int] = defaultdict(int)
    locked_lab_by_slot: dict[Any, int] = defaultdict(int)

    def _count_locked_room(*, slot_id: Any, subject_id: Any, room_id: Any | None, source: str) -> None:
        subj = subject_by_id.get(subject_id)
        if subj is None:
            return
        # Special-room locks do not consume normal room capacity.
        room = room_by_id.get(room_id) if room_id is not None else None
        if room is not None and bool(getattr(room, "is_special", False)):
            return
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
            locked_lab_by_slot[slot_id] += 1
        else:
            locked_theory_by_slot[slot_id] += 1

    # Fixed entries: include all covered lab slots.
    for fe in fixed_entries:
        subj = subject_by_id.get(getattr(fe, "subject_id", None))
        if subj is None:
            continue
        slot_id = getattr(fe, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        day, slot_idx = int(di[0]), int(di[1])
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
            block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1
            for j in range(block):
                ts = slot_by_day_index.get((day, slot_idx + j))
                if ts is None:
                    continue
                _count_locked_room(slot_id=ts.id, subject_id=getattr(fe, "subject_id", None), room_id=getattr(fe, "room_id", None), source="FIXED_ENTRY")
        else:
            _count_locked_room(slot_id=slot_id, subject_id=getattr(fe, "subject_id", None), room_id=getattr(fe, "room_id", None), source="FIXED_ENTRY")

    # Special allotments: include all covered lab slots.
    for sa in special_allotments:
        subj = subject_by_id.get(getattr(sa, "subject_id", None))
        if subj is None:
            continue
        slot_id = getattr(sa, "slot_id", None)
        if slot_id is None:
            continue
        di = slot_info.get(slot_id)
        if not di:
            continue
        day, slot_idx = int(di[0]), int(di[1])
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB":
            block = int(getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1
            for j in range(block):
                ts = slot_by_day_index.get((day, slot_idx + j))
                if ts is None:
                    continue
                _count_locked_room(slot_id=ts.id, subject_id=getattr(sa, "subject_id", None), room_id=getattr(sa, "room_id", None), source="SPECIAL_ALLOTMENT")
        else:
            _count_locked_room(slot_id=slot_id, subject_id=getattr(sa, "subject_id", None), room_id=getattr(sa, "room_id", None), source="SPECIAL_ALLOTMENT")

    for slot_id, needed in sorted(locked_theory_by_slot.items(), key=lambda kv: str(kv[0])):
        if int(needed) > int(theory_room_capacity):
            di = slot_info.get(slot_id)
            day, slot_idx = (int(di[0]), int(di[1])) if di else (None, None)
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.ROOM_CAPACITY_SHORTAGE,
                    slot_id=str(slot_id),
                    day_of_week=day,
                    slot_index=slot_idx,
                    required_rooms=int(needed),
                    available_rooms=int(theory_room_capacity),
                    room_type="THEORY",
                    explanation=(
                        f"Slot D{day} #{slot_idx} requires {int(needed)} THEORY rooms but only {int(theory_room_capacity)} normal rooms are available."
                    ),
                )
            )

    for slot_id, needed in sorted(locked_lab_by_slot.items(), key=lambda kv: str(kv[0])):
        if int(needed) > int(lab_room_capacity):
            di = slot_info.get(slot_id)
            day, slot_idx = (int(di[0]), int(di[1])) if di else (None, None)
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.ROOM_CAPACITY_SHORTAGE,
                    slot_id=str(slot_id),
                    day_of_week=day,
                    slot_index=slot_idx,
                    required_rooms=int(needed),
                    available_rooms=int(lab_room_capacity),
                    room_type="LAB",
                    explanation=(
                        f"Slot D{day} #{slot_idx} requires {int(needed)} LAB rooms but only {int(lab_room_capacity)} normal rooms are available."
                    ),
                )
            )

    # ------------------------
    # H) Special room misuse
    # ------------------------
    for fe in fixed_entries:
        rid = getattr(fe, "room_id", None)
        if rid is None:
            continue
        room = room_by_id.get(rid)
        if room is not None and bool(getattr(room, "is_special", False)):
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.SPECIAL_ROOM_MISUSE,
                    source="FIXED_ENTRY",
                    room_id=str(rid),
                    room=getattr(room, "code", None),
                    section_id=str(getattr(fe, "section_id", "")),
                    section=getattr(section_by_id.get(getattr(fe, "section_id", None)), "code", None),
                    subject_id=str(getattr(fe, "subject_id", "")),
                    subject=getattr(subject_by_id.get(getattr(fe, "subject_id", None)), "code", None),
                    explanation=(
                        f"Fixed entry uses special room {getattr(room, 'code', rid)}. Special rooms can only be used via Special Allotments."
                    ),
                )
            )

    # ------------------------
    # I) Combined group intersection empty
    # ------------------------
    # Intersection of *free* slots across the group is empty.
    for gid, sec_ids in group_sections.items():
        subj_id = group_subject.get(gid)
        subj = subject_by_id.get(subj_id) if subj_id is not None else None
        sessions_per_week = int(getattr(subj, "sessions_per_week", 0) or 0) if subj is not None else 0
        if sessions_per_week <= 0:
            continue

        intersection: set[Any] | None = None
        for sid in sec_ids:
            free = set(window_slot_ids_by_section.get(sid, set()))
            # Remove locked slot ids (fixed + special) for this section.
            for day in active_days:
                locked_indices = locked_slot_indices_by_section_day.get((sid, int(day)), set())
                if not locked_indices:
                    continue
                for idx in locked_indices:
                    ts = slot_by_day_index.get((int(day), int(idx)))
                    if ts is not None:
                        free.discard(ts.id)
            intersection = free if intersection is None else (intersection & free)

        if not intersection:
            diagnostics.append(
                _diag(
                    dtype=DiagnosticType.COMBINED_GROUP_NO_INTERSECTION,
                    group_id=str(gid),
                    subject_id=str(subj_id) if subj_id is not None else None,
                    subject=getattr(subj, "code", None) if subj is not None else None,
                    sections=[getattr(section_by_id.get(sid), "code", str(sid)) for sid in sec_ids],
                    explanation=(
                        f"Combined group ({getattr(subj, 'code', subj_id)}) for sections {', '.join([getattr(section_by_id.get(sid), 'code', str(sid)) for sid in sec_ids])} "
                        f"has no common available slot."
                    ),
                )
            )

    # If everything above produced nothing, emit a single "inconclusive" diagnostic.
    if not diagnostics:
        diagnostics.append(
            _diag(
                dtype=DiagnosticType.DIAGNOSTICS_INCONCLUSIVE,
                explanation=(
                    "CP-SAT reported INFEASIBLE, but the pre-solve diagnostic checks could not pinpoint a single deterministic blocker. "
                    "This usually means the infeasibility comes from an interaction of multiple constraints (teacher no-overlap, combined groups, electives, "
                    "per-day caps, room capacity, lab contiguity, or fixed/special locks across sections). "
                    "Next step: open Conflicts for this run and inspect the INFEASIBLE conflict details/metadata; if you share that JSON, we can add a targeted diagnostic."
                ),
                counts={
                    "sections": int(len(sections)),
                    "fixed_entries": int(len(fixed_entries)),
                    "special_allotments": int(len(special_allotments)),
                    "combined_groups": int(len(group_sections)),
                },
            )
        )

    return diagnostics
