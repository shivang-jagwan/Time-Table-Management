from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from solver.capacity_analyzer import analyze_capacity, build_capacity_data


def _safe_float_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 2)


def _duration_slots(subj: Any, override: int | None = None) -> int:
    if override is not None:
        duration = int(override or 1)
    else:
        duration_raw = getattr(subj, "duration_slots", None)
        legacy_raw = getattr(subj, "lab_block_size_slots", None)
        duration = int(duration_raw or 0) if duration_raw is not None else 0
        legacy = int(legacy_raw or 0) if legacy_raw is not None else 0
        if duration < 1:
            duration = legacy
        if legacy >= 1 and duration != legacy:
            duration = legacy
    if duration < 1:
        duration = 1
    return duration


def _build_window_slot_sets(
    *,
    sections: list[Any],
    windows: list[Any],
    slot_by_day_index: dict[tuple[int, int], Any],
) -> dict[Any, set[Any]]:
    section_id_set = {getattr(s, "id", None) for s in sections}
    out: dict[Any, set[Any]] = defaultdict(set)
    for w in windows:
        sec_id = getattr(w, "section_id", None)
        if sec_id not in section_id_set:
            continue
        day = int(getattr(w, "day_of_week", 0))
        start = int(getattr(w, "start_slot_index", 0))
        end = int(getattr(w, "end_slot_index", -1))
        for slot_idx in range(start, end + 1):
            slot_id = slot_by_day_index.get((day, slot_idx))
            if slot_id is not None:
                out[sec_id].add(slot_id)
    return out


def calculate_pre_solve_metrics(
    db: Session,
    *,
    program_id: Any,
    academic_year_id: Any | None,
    sections: list[Any],
    tenant_id: Any | None,
) -> dict[str, Any]:
    """Compute transparent pre-solve scheduling diagnostics.

    This is a read-only analyzer and does not modify database state.
    """
    capacity_data = build_capacity_data(
        db,
        program_id=program_id,
        academic_year_id=academic_year_id,
        sections=sections,
        tenant_id=tenant_id,
    )
    capacity_result = analyze_capacity(capacity_data)
    summary = capacity_result.get("summary", {}) or {}

    teacher_by_id: dict[Any, Any] = dict(capacity_data.get("teachers_by_id") or {})
    subject_by_id: dict[Any, Any] = dict(capacity_data.get("subjects_by_id") or {})
    section_list: list[Any] = list(capacity_data.get("sections") or [])
    section_by_id: dict[Any, Any] = dict(capacity_data.get("sections_by_id") or {})
    mapped_subject_ids_by_section: dict[Any, list[Any]] = dict(
        capacity_data.get("mapped_subject_ids_by_section") or {}
    )
    sessions_per_week_by_section_subject: dict[tuple[Any, Any], int] = dict(
        capacity_data.get("sessions_per_week_by_section_subject") or {}
    )
    duration_by_section_subject: dict[tuple[Any, Any], int] = dict(
        capacity_data.get("duration_by_section_subject")
        or capacity_data.get("lab_block_by_section_subject")
        or {}
    )
    blocks_by_section: dict[Any, list[Any]] = dict(capacity_data.get("blocks_by_section") or {})
    block_subject_pairs_by_block: dict[Any, list[tuple[Any, Any]]] = dict(
        capacity_data.get("block_subject_pairs_by_block") or {}
    )
    assigned_teacher_by_section_subject: dict[tuple[Any, Any], Any] = dict(
        capacity_data.get("assigned_teacher_by_section_subject") or {}
    )
    slots: list[Any] = list(capacity_data.get("slots") or [])
    rooms: list[Any] = list(capacity_data.get("rooms") or [])
    windows: list[Any] = list(capacity_data.get("windows") or [])
    slot_by_day_index: dict[tuple[int, int], Any] = dict(capacity_data.get("slot_by_day_index") or {})

    required_by_teacher = {str(k): int(v) for k, v in (summary.get("required_by_teacher") or {}).items()}
    available_by_teacher = {str(k): int(v) for k, v in (summary.get("available_by_teacher") or {}).items()}
    required_by_section = {str(k): int(v) for k, v in (summary.get("required_by_section") or {}).items()}
    available_by_section = {str(k): int(v) for k, v in (summary.get("available_by_section") or {}).items()}

    # Build direct section/session demand to avoid sparse-summary edge cases.
    direct_required_by_section: dict[str, int] = defaultdict(int)
    direct_required_by_teacher: dict[str, int] = defaultdict(int)
    direct_required_by_room_type: dict[str, int] = defaultdict(int)
    for sec in section_list:
        sec_id = getattr(sec, "id", None)
        if sec_id is None:
            continue
        sid = str(sec_id)
        subj_ids = list(mapped_subject_ids_by_section.get(sec_id, []) or [])
        for subj_id in subj_ids:
            subj = subject_by_id.get(subj_id)
            if subj is None:
                continue
            sessions = int(
                sessions_per_week_by_section_subject.get((sec_id, subj_id), getattr(subj, "sessions_per_week", 0) or 0)
                or 0
            )
            if sessions <= 0:
                continue
            duration = _duration_slots(subj, duration_by_section_subject.get((sec_id, subj_id)))
            required_slots = int(sessions) * int(duration)
            direct_required_by_section[sid] += int(required_slots)
            subj_type = str(getattr(subj, "subject_type", "THEORY")).upper()
            if subj_type == "LAB":
                direct_required_by_room_type["LAB"] += int(required_slots)
            else:
                direct_required_by_room_type["THEORY"] += int(required_slots)

            tid = assigned_teacher_by_section_subject.get((sec_id, subj_id))
            if tid is not None:
                direct_required_by_teacher[str(tid)] += int(required_slots)

        # If section uses elective blocks (and no direct section-subject mapping),
        # each block contributes one session stream per week for the section.
        if not subj_ids:
            for block_id in blocks_by_section.get(sec_id, []) or []:
                pairs = block_subject_pairs_by_block.get(block_id, []) or []
                if not pairs:
                    continue
                subj = subject_by_id.get(pairs[0][0])
                if subj is None:
                    continue
                sessions = int(getattr(subj, "sessions_per_week", 0) or 0)
                if sessions <= 0:
                    continue
                required_slots = int(sessions) * int(_duration_slots(subj))
                direct_required_by_section[sid] += int(required_slots)
                subj_type = str(getattr(subj, "subject_type", "THEORY")).upper()
                if subj_type == "LAB":
                    direct_required_by_room_type["LAB"] += int(required_slots)
                else:
                    direct_required_by_room_type["THEORY"] += int(required_slots)

    if direct_required_by_section:
        required_by_section = {k: int(v) for k, v in direct_required_by_section.items()}
    if direct_required_by_teacher:
        required_by_teacher = {k: int(v) for k, v in direct_required_by_teacher.items()}

    teacher_load: list[dict[str, Any]] = []
    for tid, required in sorted(required_by_teacher.items(), key=lambda kv: kv[0]):
        teacher = teacher_by_id.get(tid)
        if teacher is None:
            for obj in teacher_by_id.values():
                if str(getattr(obj, "id", "")) == tid:
                    teacher = obj
                    break

        max_limit = int(available_by_teacher.get(tid, 0) or 0)
        teacher_load.append(
            {
                "teacher_id": tid,
                "teacher_name": str(getattr(teacher, "full_name", None) or getattr(teacher, "code", tid)),
                "required_lectures": int(required),
                "max_lectures_limit": int(max_limit),
                "overload": max(0, int(required) - int(max_limit)),
            }
        )

    section_summary: list[dict[str, Any]] = []
    for sec in sorted(section_list, key=lambda s: str(getattr(s, "code", ""))):
        sid = str(getattr(sec, "id", ""))
        required = int(required_by_section.get(sid, 0) or 0)
        available = int(available_by_section.get(sid, 0) or 0)
        section_summary.append(
            {
                "section_id": sid,
                "section_code": str(getattr(sec, "code", sid)),
                "total_classes_required": int(required),
                "available_slots": int(available),
                "infeasible": bool(required > available),
                "shortage": max(0, int(required) - int(available)),
            }
        )

    # Parallel room requirement based on active windows.
    window_slots_by_section = _build_window_slot_sets(
        sections=section_list,
        windows=windows,
        slot_by_day_index=slot_by_day_index,
    )
    active_section_count_by_slot: dict[Any, int] = defaultdict(int)
    for sec in section_list:
        sid = getattr(sec, "id", None)
        if sid is None:
            continue
        for slot_id in window_slots_by_section.get(sid, set()):
            active_section_count_by_slot[slot_id] += 1

    max_parallel_sections = max((int(v) for v in active_section_count_by_slot.values()), default=0)

    total_rooms = int(
        len([r for r in rooms if bool(getattr(r, "is_active", True)) and not bool(getattr(r, "is_special", False))])
    )
    lab_rooms = int(
        len(
            [
                r
                for r in rooms
                if bool(getattr(r, "is_active", True))
                and not bool(getattr(r, "is_special", False))
                and str(getattr(r, "room_type", "")).upper() == "LAB"
            ]
        )
    )

    required_by_room_type = {k: int(v) for k, v in (summary.get("required_by_room_type") or {}).items()}
    if direct_required_by_room_type:
        required_by_room_type = {k: int(v) for k, v in direct_required_by_room_type.items()}
    available_by_room_type = {k: int(v) for k, v in (summary.get("available_by_room_type") or {}).items()}

    total_slots = int(len(slots))
    total_required_classes = int(sum(required_by_section.values()))
    total_section_capacity = int(sum(available_by_section.values()))

    utilization = {
        "total_slots": total_slots,
        "total_required_classes": total_required_classes,
        "total_capacity": total_section_capacity,
        "percentage": _safe_float_pct(total_required_classes, total_section_capacity),
    }

    room_analysis = {
        "total_rooms": int(total_rooms),
        "parallel_required": int(max_parallel_sections),
        "deficit": max(0, int(max_parallel_sections) - int(total_rooms)),
        "lab_required_slots": int(required_by_room_type.get("LAB", 0)),
        "lab_available_slots": int(available_by_room_type.get("LAB", 0)),
        "lab_rooms": int(lab_rooms),
    }

    bottlenecks: list[str] = []
    for row in sorted(teacher_load, key=lambda r: int(r["overload"]), reverse=True):
        if int(row["overload"]) > 0:
            bottlenecks.append(
                f"Teacher {row['teacher_name']} overloaded by {int(row['overload'])} lecture(s)."
            )

    if int(room_analysis["deficit"]) > 0:
        bottlenecks.append(
            f"Room shortage: peak parallel need is {room_analysis['parallel_required']} vs {room_analysis['total_rooms']} available."
        )

    for row in section_summary:
        if bool(row["infeasible"]):
            bottlenecks.append(
                f"Section {row['section_code']} requires {row['total_classes_required']} classes but has {row['available_slots']} slots."
            )

    for issue in capacity_result.get("issues", []) or []:
        issue_type = str(issue.get("type", ""))
        if issue_type in {"SUBJECT_ROOM_RESTRICTION_CONFLICT", "COMBINED_DOMAIN_COLLAPSE"}:
            resource = str(issue.get("resource", issue_type))
            shortage = int(issue.get("shortage", 0) or 0)
            if shortage > 0:
                bottlenecks.append(f"{resource} has impossible allocation (shortage {shortage}).")

    # Keep output concise and stable.
    deduped_bottlenecks: list[str] = []
    seen: set[str] = set()
    for msg in bottlenecks:
        if msg in seen:
            continue
        seen.add(msg)
        deduped_bottlenecks.append(msg)

    return {
        "teacher_load": teacher_load,
        "section_summary": section_summary,
        "room_analysis": room_analysis,
        "utilization": utilization,
        "bottlenecks": deduped_bottlenecks,
        "capacity_summary": summary,
    }
