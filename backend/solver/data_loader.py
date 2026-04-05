"""Load all data from the database into SolverContext.

Extracts lines ~120-370 from the original monolithic _solve_program:
sections, slots, rooms, subjects, teachers, teacher assignments,
fixed entries, special allotments, curriculum, elective blocks,
allowed slots, combined groups.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.tenant import where_tenant
from core.db import table_exists
from models.combined_group import CombinedGroup
from models.combined_group_section import CombinedGroupSection
from models.elective_block import ElectiveBlock
from models.elective_block_subject import ElectiveBlockSubject
from models.curriculum_subject import CurriculumSubject
from models.room import Room
from models.section import Section
from models.section_elective_block import SectionElectiveBlock
from models.section_subject import SectionSubject
from models.section_time_window import SectionTimeWindow
from models.subject import Subject
from models.subject_allowed_room import SubjectAllowedRoom
from models.teacher import Teacher
from models.teacher_time_window import TeacherTimeWindow
from models.teacher_subject_section import TeacherSubjectSection
from models.time_slot import TimeSlot
from models.track_subject import TrackSubject
from models.fixed_timetable_entry import FixedTimetableEntry
from models.special_allotment import SpecialAllotment
from models.timetable_entry import TimetableEntry

from solver.context import SolverContext


def load_all(ctx: SolverContext) -> None:
    """Populate *ctx* with all data required for the solve."""
    db = ctx.db
    tenant_id = ctx.tenant_id
    program_id = ctx.program_id
    academic_year_id = ctx.academic_year_id

    # --- Sections ------------------------------------------------------------
    q_sections = (
        select(Section)
        .where(Section.program_id == program_id)
        .where(Section.is_active.is_(True))
    )
    q_sections = where_tenant(q_sections, Section, tenant_id)
    if academic_year_id is not None:
        q_sections = q_sections.where(Section.academic_year_id == academic_year_id)
    if ctx.section_id_subset:
        q_sections = q_sections.where(Section.id.in_(list(ctx.section_id_subset)))

    ctx.sections = db.execute(q_sections.order_by(Section.code)).scalars().all()
    ctx.section_year_by_id = {s.id: s.academic_year_id for s in ctx.sections}
    ctx.solve_year_ids = sorted({s.academic_year_id for s in ctx.sections})

    # --- Time slots ----------------------------------------------------------
    ctx.slots = db.execute(where_tenant(select(TimeSlot), TimeSlot, tenant_id)).scalars().all()
    ctx.slot_by_day_index = {(s.day_of_week, s.slot_index): s for s in ctx.slots}
    ctx.slot_info = {s.id: (s.day_of_week, s.slot_index) for s in ctx.slots}
    ctx.lunch_slot_ids = {s.id for s in ctx.slots if bool(getattr(s, "is_lunch_break", False))}
    for s in ctx.slots:
        ctx.slots_by_day[s.day_of_week].append(s)
    for d in ctx.slots_by_day:
        ctx.slots_by_day[d].sort(key=lambda x: x.slot_index)

    # --- Section time windows ------------------------------------------------
    q_windows = select(SectionTimeWindow).where(
        SectionTimeWindow.section_id.in_([s.id for s in ctx.sections])
    )
    q_windows = where_tenant(q_windows, SectionTimeWindow, tenant_id)
    windows = db.execute(q_windows).scalars().all()
    for w in windows:
        ctx.windows_by_section[w.section_id].append(w)

    # --- Rooms ---------------------------------------------------------------
    q_rooms = where_tenant(select(Room).where(Room.is_active.is_(True)), Room, tenant_id)
    ctx.rooms_all = db.execute(q_rooms).scalars().all()
    ctx.room_by_id = {r.id: r for r in ctx.rooms_all}
    for r in ctx.rooms_all:
        if bool(getattr(r, "is_special", False)):
            continue
        ctx.rooms_by_type[str(r.room_type)].append(r)

    # --- Subjects ------------------------------------------------------------
    q_subjects = (
        select(Subject)
        .where(Subject.program_id == program_id)
        .where(Subject.is_active.is_(True))
    )
    if ctx.solve_year_ids:
        q_subjects = q_subjects.where(Subject.academic_year_id.in_(ctx.solve_year_ids))
    q_subjects = where_tenant(q_subjects, Subject, tenant_id)
    ctx.subjects = db.execute(q_subjects).scalars().all()
    ctx.subject_by_id = {s.id: s for s in ctx.subjects}

    # --- Curriculum subjects (scheduling params per program/year/track) ------
    _load_curriculum_subjects(ctx)

    # --- Subject → allowed rooms (optional; table may not exist yet) ---------
    _load_subject_allowed_rooms(ctx)

    # --- Teachers ------------------------------------------------------------
    q_teachers = where_tenant(select(Teacher).where(Teacher.is_active.is_(True)), Teacher, tenant_id)
    ctx.teachers = db.execute(q_teachers).scalars().all()
    ctx.teacher_by_id = {t.id: t for t in ctx.teachers}

    # --- Teacher time windows ------------------------------------------------
    # Load availability windows after teachers so strict/soft windows are
    # available for slot pruning and preference penalties.
    if ctx.teachers:
        q_twins = select(TeacherTimeWindow).where(
            TeacherTimeWindow.teacher_id.in_([t.id for t in ctx.teachers])
        )
        q_twins = where_tenant(q_twins, TeacherTimeWindow, tenant_id)
        twin_rows = db.execute(q_twins).scalars().all()
        for tw in twin_rows:
            ctx.teacher_windows_by_id[tw.teacher_id].append(tw)

    # --- Teacher → section-subject assignment --------------------------------
    if ctx.sections:
        rows = db.execute(
            where_tenant(
                select(
                    TeacherSubjectSection.section_id,
                    TeacherSubjectSection.subject_id,
                    TeacherSubjectSection.teacher_id,
                )
                .where(TeacherSubjectSection.section_id.in_([s.id for s in ctx.sections]))
                .where(TeacherSubjectSection.is_active.is_(True)),
                TeacherSubjectSection,
                tenant_id,
            )
        ).all()
        for sec_id, subj_id, teacher_id in rows:
            ctx.assigned_teacher_by_section_subject.setdefault((sec_id, subj_id), teacher_id)

    # --- Fixed timetable entries ---------------------------------------------
    ctx.fixed_entries = (
        db.execute(
            where_tenant(
                select(FixedTimetableEntry)
                .where(FixedTimetableEntry.section_id.in_([s.id for s in ctx.sections]))
                .where(FixedTimetableEntry.is_active.is_(True)),
                FixedTimetableEntry,
                tenant_id,
            )
        )
        .scalars()
        .all()
    )

    # --- Special allotments --------------------------------------------------
    ctx.special_allotments = (
        db.execute(
            where_tenant(
                select(SpecialAllotment)
                .where(SpecialAllotment.section_id.in_([s.id for s in ctx.sections]))
                .where(SpecialAllotment.is_active.is_(True)),
                SpecialAllotment,
                tenant_id,
            )
        )
        .scalars()
        .all()
    )

    # --- Curriculum per section (SectionSubject or TrackSubject) --------------
    section_subject_rows = db.execute(
        where_tenant(
            select(SectionSubject.section_id, SectionSubject.subject_id).where(
                SectionSubject.section_id.in_([s.id for s in ctx.sections])
            ),
            SectionSubject,
            tenant_id,
        )
    ).all()
    mapped_subjects_by_section: dict[Any, list[Any]] = defaultdict(list)
    for sec_id, subj_id in section_subject_rows:
        mapped_subjects_by_section[sec_id].append(subj_id)

    for section in ctx.sections:
        mapped = mapped_subjects_by_section.get(section.id, [])
        if mapped:
            ctx.section_required[section.id] = [(sid, None) for sid in mapped]
            continue

        track_rows = (
            db.execute(
                where_tenant(
                    select(TrackSubject)
                    .where(TrackSubject.program_id == program_id)
                    .where(TrackSubject.academic_year_id == section.academic_year_id)
                    .where(TrackSubject.track == section.track),
                    TrackSubject,
                    tenant_id,
                )
            )
            .scalars()
            .all()
        )
        mandatory = [r for r in track_rows if not r.is_elective]
        ctx.section_required[section.id] = [(r.subject_id, r.sessions_override) for r in mandatory]

    # --- Elective blocks -----------------------------------------------------
    _load_elective_blocks(ctx)

    # --- Allowed slots per section -------------------------------------------
    _load_allowed_slots(ctx)

    # --- Combined groups (v2 + legacy) ---------------------------------------
    _load_combined_groups(ctx)

    # --- Existing run occupancy (for decomposed append mode) ------------------
    _load_existing_run_room_events(ctx)

    # --- Build integer index maps (OPTIMIZATION) -----------------------------
    # Must come after all entities are loaded so the maps are complete.
    _build_index_maps(ctx)

    # --- Build room sort cache (OPTIMIZATION Task 5) -------------------------
    # Must come after rooms and sections are loaded.
    _build_room_cache(ctx)


def _load_curriculum_subjects(ctx: SolverContext) -> None:
    """Populate ctx.curriculum_by_track_subject and ctx.curriculum_by_subject_id.

    Loads all curriculum_subjects records for the current solve scope
    (program_id + academic_year_ids).  If the table does not yet exist
    (migration not applied) this is a no-op — the solver falls back to reading
    sessions_per_week / max_per_day / lab_block_size_slots directly from the
    subjects table via the ctx.sessions_for() / ctx.max_per_day_for() /
    ctx.lab_block_for() helper methods.
    """
    db = ctx.db
    tenant_id = ctx.tenant_id
    if not table_exists(db, "curriculum_subjects"):
        return

    q = (
        select(CurriculumSubject)
        .where(CurriculumSubject.program_id == ctx.program_id)
    )
    if ctx.solve_year_ids:
        q = q.where(CurriculumSubject.academic_year_id.in_(ctx.solve_year_ids))
    q = where_tenant(q, CurriculumSubject, tenant_id)
    rows = db.execute(q).scalars().all()

    for cs in rows:
        track = str(cs.track)
        ctx.curriculum_by_track_subject[(track, cs.subject_id)] = cs
        # CORE wins over any other track for the flat fallback lookup
        if track == "CORE" or cs.subject_id not in ctx.curriculum_by_subject_id:
            ctx.curriculum_by_subject_id[cs.subject_id] = cs


def _load_subject_allowed_rooms(ctx: SolverContext) -> None:
    """Load subject_allowed_rooms into ctx.allowed_rooms_by_subject.

    If the table does not exist yet (e.g. migration not applied), this is a
    no-op so the solver continues working without the feature.
    """
    db = ctx.db
    tenant_id = ctx.tenant_id

    if not table_exists(db, "subject_allowed_rooms"):
        return
    if not ctx.subjects:
        return

    subject_ids = [s.id for s in ctx.subjects]
    q = (
        select(SubjectAllowedRoom.subject_id, SubjectAllowedRoom.room_id, SubjectAllowedRoom.is_exclusive)
        .where(SubjectAllowedRoom.subject_id.in_(subject_ids))
    )
    q = where_tenant(q, SubjectAllowedRoom, tenant_id)
    for subj_id, room_id, is_exclusive in db.execute(q).all():
        ctx.allowed_rooms_by_subject.setdefault(subj_id, []).append(room_id)
        if bool(is_exclusive):
            ctx.exclusive_rooms_by_subject[subj_id].add(room_id)
            ctx.exclusive_subject_by_room.setdefault(room_id, subj_id)


def _load_elective_blocks(ctx: SolverContext) -> None:
    db = ctx.db
    tenant_id = ctx.tenant_id

    use_elective_blocks = (
        table_exists(db, "elective_blocks")
        and table_exists(db, "elective_block_subjects")
        and table_exists(db, "section_elective_blocks")
    )

    if not use_elective_blocks or not ctx.sections:
        return

    sec_block_rows = db.execute(
        where_tenant(
            select(SectionElectiveBlock.section_id, SectionElectiveBlock.block_id)
            .where(SectionElectiveBlock.section_id.in_([s.id for s in ctx.sections])),
            SectionElectiveBlock,
            tenant_id,
        )
    ).all()
    block_ids = sorted({bid for _sid, bid in sec_block_rows})
    for sid, bid in sec_block_rows:
        ctx.blocks_by_section[sid].append(bid)
        ctx.sections_by_block[bid].append(sid)

    if not block_ids:
        return

    blocks = (
        db.execute(
            where_tenant(
                select(ElectiveBlock).where(ElectiveBlock.id.in_(block_ids)),
                ElectiveBlock,
                tenant_id,
            )
        )
        .scalars()
        .all()
    )
    ctx.elective_block_by_id = {b.id: b for b in blocks}

    bsubs = (
        db.execute(
            where_tenant(
                select(ElectiveBlockSubject).where(ElectiveBlockSubject.block_id.in_(block_ids)),
                ElectiveBlockSubject,
                tenant_id,
            )
        )
        .scalars()
        .all()
    )
    for row in bsubs:
        ctx.block_subject_pairs_by_block[row.block_id].append((row.subject_id, row.teacher_id))

    for sid, bids in ctx.blocks_by_section.items():
        for bid in bids:
            for subj_id, _tid in ctx.block_subject_pairs_by_block.get(bid, []):
                ctx.elective_block_by_section_subject.setdefault((sid, subj_id), bid)

    # Prevent double scheduling: subjects covered by elective blocks should not
    # also be treated as normal section_required theory subjects.
    for sid, bids in ctx.blocks_by_section.items():
        block_subject_ids: set[Any] = set()
        for bid in bids:
            for subj_id, _tid in ctx.block_subject_pairs_by_block.get(bid, []):
                block_subject_ids.add(subj_id)
        if not block_subject_ids:
            continue
        existing = ctx.section_required.get(sid, [])
        if not existing:
            continue
        ctx.section_required[sid] = [
            (subj_id, sessions_override)
            for subj_id, sessions_override in existing
            if subj_id not in block_subject_ids
        ]


def _load_allowed_slots(ctx: SolverContext) -> None:
    db = ctx.db
    tenant_id = ctx.tenant_id

    for section in ctx.sections:
        for w in ctx.windows_by_section.get(section.id, []):
            for si in range(w.start_slot_index, w.end_slot_index + 1):
                ts = ctx.slot_by_day_index.get((w.day_of_week, si))
                if ts is not None and ts.id not in ctx.lunch_slot_ids:
                    ctx.allowed_slots_by_section[section.id].add(ts.id)

    # Precompute allowed slot indices per (section, day)
    for section in ctx.sections:
        for slot_id in ctx.allowed_slots_by_section.get(section.id, set()):
            day, slot_idx = ctx.slot_info.get(slot_id, (None, None))
            if day is None or slot_idx is None:
                continue
            ctx.allowed_slot_indices_by_section_day[(section.id, int(day))].append(int(slot_idx))
    for key, arr in ctx.allowed_slot_indices_by_section_day.items():
        arr.sort()


def _load_combined_groups(ctx: SolverContext) -> None:
    db = ctx.db
    tenant_id = ctx.tenant_id

    q_combined = (
        select(
            CombinedGroup.id,
            CombinedGroup.subject_id,
            CombinedGroup.teacher_id,
            CombinedGroupSection.section_id,
        )
        .join(CombinedGroupSection, CombinedGroupSection.combined_group_id == CombinedGroup.id)
        .join(Subject, Subject.id == CombinedGroup.subject_id)
        .where(Subject.program_id == ctx.program_id)
        .where(Subject.is_active.is_(True))
    )
    if ctx.solve_year_ids:
        q_combined = q_combined.where(
            CombinedGroup.academic_year_id.in_(ctx.solve_year_ids)
        ).where(Subject.academic_year_id.in_(ctx.solve_year_ids))
    q_combined = where_tenant(q_combined, CombinedGroup, tenant_id)
    q_combined = where_tenant(q_combined, CombinedGroupSection, tenant_id)
    q_combined = where_tenant(q_combined, Subject, tenant_id)
    combined_rows = db.execute(q_combined).all()

    group_sections: dict[Any, list[Any]] = defaultdict(list)
    group_subject: dict[Any, Any] = {}
    group_teacher_id: dict[Any, Any] = {}
    for gid, subj_id, teacher_id, sec_id in combined_rows:
        group_sections[gid].append(sec_id)
        group_subject[gid] = subj_id
        if gid not in group_teacher_id:
            group_teacher_id[gid] = teacher_id

    solve_section_ids = {s.id for s in ctx.sections}
    for gid in list(group_sections.keys()):
        subj_id = group_subject.get(gid)
        if subj_id is None:
            del group_sections[gid]
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is None or str(subj.subject_type) != "THEORY":
            del group_sections[gid]
            continue

        filtered = [sid for sid in group_sections[gid] if sid in solve_section_ids]
        if len(set(filtered)) < 2:
            del group_sections[gid]
            continue
        filtered = list(dict.fromkeys(filtered))
        group_sections[gid] = filtered
        for sid in filtered:
            ctx.combined_gid_by_sec_subj[(sid, subj_id)] = gid

    ctx.group_sections = group_sections
    ctx.group_subject = group_subject
    ctx.group_teacher_id = group_teacher_id


def _load_existing_run_room_events(ctx: SolverContext) -> None:
    """Load persisted room occupancy rows for the current run once, up-front."""

    db = ctx.db
    tenant_id = ctx.tenant_id
    q_existing = (
        select(
            TimetableEntry.room_id,
            TimetableEntry.slot_id,
            TimetableEntry.combined_class_id,
        )
        .where(TimetableEntry.run_id == ctx.run.id)
    )
    q_existing = where_tenant(q_existing, TimetableEntry, tenant_id)
    ctx.existing_run_room_events = list(db.execute(q_existing).all())


# ── Index maps & pruned slot computation (OPTIMIZATION) ──────────────────────


def _build_room_cache(ctx: SolverContext) -> None:
    """Pre-sort room lists and build per-section best-fit orderings.

    OPTIMIZATION (Task 5): pick_room() previously called
      list(ctx.rooms_by_type.get(...))   — copy each call
      for s in ctx.sections: if s.id == sec_id  — O(S) scan each call
      fits.sort(); too_small.sort()       — O(R log R) each call

    By computing these once here the per-call cost drops to O(1) dict
    lookup + O(R) scan with no copying or sorting.
    """
    cap = lambda r: int(getattr(r, "capacity", 0) or 0)

    ctx.lab_rooms_sorted = sorted(ctx.rooms_by_type.get("LAB", []), key=cap)
    ctx.classroom_rooms_sorted = sorted(ctx.rooms_by_type.get("CLASSROOM", []), key=cap)
    ctx.lt_rooms_sorted = sorted(ctx.rooms_by_type.get("LT", []), key=cap)

    # LT-first: used by pick_lt_room (elective/combined classes)
    ctx.lt_plus_classroom_rooms_sorted = [*ctx.lt_rooms_sorted, *ctx.classroom_rooms_sorted]

    # Theory rooms: CLASSROOM + LT merged and sorted by capacity ASC.
    # This is the base ordering for sections without a known strength.
    ctx.theory_rooms_sorted = sorted(
        [*ctx.rooms_by_type.get("CLASSROOM", []), *ctx.rooms_by_type.get("LT", [])],
        key=cap,
    )

    # Per-section best-fit ordering.
    # For each section we compute two lists:
    #   (section.id, "THEORY")  — best-fit CLASSROOM+LT rooms
    #   (section.id, "LAB")     — best-fit LAB rooms
    # A "best-fit" ordering is: rooms that fit (cap >= strength) sorted cap
    # ASC first, then rooms that are too small sorted cap DESC (best effort).
    # If strength is unknown/0 we use the plain sorted base list.
    for section in ctx.sections:
        strength = int(getattr(section, "strength", 0) or 0)
        for tag, base in [("LAB", ctx.lab_rooms_sorted), ("THEORY", ctx.theory_rooms_sorted)]:
            if strength > 0:
                # base is already sorted cap ASC, so:
                #   fits = rooms with cap >= strength (already in ASC order)
                #   too_small = rooms with cap < strength in DESC order
                #              = reversed slice of the prefix of base
                fits = [r for r in base if cap(r) >= strength]
                too_small = [r for r in reversed(base) if cap(r) < strength]
                ctx.room_candidates_by_section[(section.id, tag)] = fits + too_small
            else:
                ctx.room_candidates_by_section[(section.id, tag)] = base

    # Also build section_by_id for O(1) lookups elsewhere.
    ctx.section_by_id = {s.id: s for s in ctx.sections}


def _build_index_maps(ctx: SolverContext) -> None:
    """Build dense integer index maps for all solver entities.

    OPTIMIZATION: CP-SAT model-building involves millions of dict lookups.
    UUID strings are 36-character objects with expensive hashing.  Mapping
    everything to dense ints (0, 1, 2, …) reduces per-lookup cost and also
    makes tuple keys smaller, which matters for the large x/lab_start dicts.

    The maps are stored in ctx and used exclusively inside variables.py,
    constraints.py, and objective.py.  result_writer.py and room_assigner.py
    keep using UUID keys so no DB-facing code changes.
    """
    for i, s in enumerate(ctx.sections):
        ctx.section_idx[s.id] = i
        ctx.idx_to_section[i] = s.id

    for i, s in enumerate(ctx.subjects):
        ctx.subject_idx[s.id] = i
        ctx.idx_to_subject[i] = s.id

    for i, t in enumerate(ctx.teachers):
        ctx.teacher_idx[t.id] = i
        ctx.idx_to_teacher[i] = t.id

    # Sort slots deterministically: day ASC, slot_index ASC
    sorted_slots = sorted(ctx.slots, key=lambda ts: (ts.day_of_week, ts.slot_index))
    for i, ts in enumerate(sorted_slots):
        ctx.slot_idx_map[ts.id] = i
        ctx.idx_to_slot[i] = ts.id

    for i, r in enumerate(ctx.rooms_all):
        ctx.room_idx[r.id] = i
        ctx.idx_to_room[i] = r.id


def build_pruned_slots(ctx: SolverContext) -> None:
    """Compute pruned slot sets for all variable types — the key domain-pruning step.

    This function is called by cp_sat_solver._solve_program() AFTER
    apply_pre_solve_locks() so that teacher_disallowed_slot_ids is already
    populated.

    PHASE 7 ENHANCEMENTS (2026-03):
      Additional domain pruning for room-restricted subjects:
      • If a subject has allowed_rooms restrictions, verify at least one
        compatible room exists (warn if not, but don't prune slots — room
        assignment is post-solve and greedy)
      • Track domain reduction effectiveness metrics

    Stage 1 — Per-(section, subject) pruning (stored in valid_slots_by_section_subject):
      Filters out slots that violate any of:
        • section time window (captured by allowed_slots_by_section)
        • teacher off-day / locked slots (teacher_disallowed_slot_ids)
        • not already locked by a special-allotment / fixed-entry
        • for LAB subjects: start positions where the full contiguous block
          does NOT fit within the same day's allowed slots

    Stage 2 — Combined-group pruning (stored in valid_slots_for_combined_group):
      For each combined THEORY group, computes the intersection of allowed
      slots across all member sections and removes teacher-blocked slots.
      _create_combined_theory_vars reads these pre-computed lists directly.

    Stage 3 — Elective-batch pruning (stored in valid_slots_for_elective_batch):
      For each (block, batch), intersects the allowed slots of all batch
      sections and removes all elective-teacher-blocked slots.
      _create_elective_block_vars reads these pre-computed lists directly.

    RESULT: CP-SAT variable creation iterates only valid slots for every
    variable type, cutting total variable count by 40–70% on typical datasets.
    With Phase 7 enhancements: additional early-warning diagnostics for
    likely infeasibility scenarios.
    """
    # --- FIX 2: Room occupancy pre-pruning ---
    from collections import Counter

    theory_rooms = len(ctx.rooms_by_type.get("CLASSROOM", [])) + len(ctx.rooms_by_type.get("LT", []))
    lab_rooms = len(ctx.rooms_by_type.get("LAB", []))

    # Pre-count existing locked occupancy per slot (from fixed_entries / special_allotments)
    locked_theory_per_slot = Counter()
    locked_lab_per_slot = Counter()
    for entry in getattr(ctx, "fixed_entries", []):
        subj = ctx.subject_by_id.get(getattr(entry, "subject_id", None))
        if subj is None:
            continue
        if str(getattr(subj, "subject_type", "")) == "LAB":
            locked_lab_per_slot[getattr(entry, "slot_id", None)] += 1
        else:
            locked_theory_per_slot[getattr(entry, "slot_id", None)] += 1

    slot_ids = [s.id for s in getattr(ctx, "slots", [])]
    ctx._slot_theory_headroom = {
        slot_id: max(0, theory_rooms - locked_theory_per_slot.get(slot_id, 0))
        for slot_id in slot_ids
    }
    ctx._slot_lab_headroom = {
        slot_id: max(0, lab_rooms - locked_lab_per_slot.get(slot_id, 0))
        for slot_id in slot_ids
    }

    dallowed = ctx.teacher_disallowed_slot_ids  # teacher_id → set[slot_id]

    for section in ctx.sections:
        sec_id = section.id
        allowed: set[Any] = ctx.allowed_slots_by_section.get(sec_id, set())
        if not allowed:
            continue

        for subject_id, _sessions_override in ctx.section_required.get(sec_id, []):
            subj = ctx.subject_by_id.get(subject_id)
            if subj is None:
                continue

            subj_type = str(getattr(subj, "subject_type", "THEORY") or "THEORY")
            slot_headroom = ctx._slot_lab_headroom if subj_type == "LAB" else ctx._slot_theory_headroom

            teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subject_id))
            if teacher_id is None:
                continue

            teacher_blocked: set[Any] = dallowed.get(teacher_id, set())
            track = str(getattr(section, "track", "CORE") or "CORE")
            block = int(ctx.duration_for(subject_id, track=track) or 1)
            if block < 1:
                block = 1

            if block <= 1:
                pruned_single = [
                    slot_id for slot_id in sorted(allowed)
                    if slot_id not in teacher_blocked and slot_headroom.get(slot_id, 0) > 0
                ]
                ctx.valid_slots_by_section_subject[(sec_id, subject_id)] = pruned_single
                continue

            pruned: list[Any] = []
            from solver.pre_solve_locks import contiguous_starts
            for day in range(6):
                indices = ctx.allowed_slot_indices_by_section_day.get((sec_id, day), [])
                if len(indices) < block:
                    continue
                for start_idx in contiguous_starts(indices, block):
                    ok = True
                    for j in range(block):
                        ts = ctx.slot_by_day_index.get((day, start_idx + j))
                        if (
                            ts is None
                            or ts.id in teacher_blocked
                            or ts.id not in allowed
                            or slot_headroom.get(ts.id, 0) <= 0
                        ):
                            ok = False
                            break
                    if not ok:
                        continue
                    start_ts = ctx.slot_by_day_index.get((day, start_idx))
                    if start_ts is not None:
                        pruned.append(start_ts.id)
            ctx.valid_slots_by_section_subject[(sec_id, subject_id)] = pruned


    # ── Combined-group pruning ────────────────────────────────────────────
    # Pre-compute the valid slot list for each combined THEORY group so that
    # _create_combined_theory_vars can use a direct lookup instead of
    # recomputing a set intersection at model-build time.
    for group_id, sec_ids in ctx.group_sections.items():
        subj_id = ctx.group_subject.get(group_id)
        if subj_id is None:
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is None or str(subj.subject_type) != "THEORY":
            continue

        assigned_teacher_id = ctx.group_teacher_id.get(group_id)
        if assigned_teacher_id is None:
            # Legacy fallback: derive teacher from per-section assignments.
            for sid in sec_ids:
                tid = ctx.assigned_teacher_by_section_subject.get((sid, subj_id))
                if tid is None:
                    assigned_teacher_id = None
                    break
                if assigned_teacher_id is None:
                    assigned_teacher_id = tid
                elif assigned_teacher_id != tid:
                    assigned_teacher_id = None
                    break
        if assigned_teacher_id is None:
            ctx.valid_slots_for_combined_group[group_id] = []
            continue

        duration_values: set[int] = set()
        for sid in sec_ids:
            section = ctx.section_by_id.get(sid)
            track = str(getattr(section, "track", "CORE") or "CORE")
            duration_values.add(max(1, int(ctx.duration_for(subj_id, track=track) or 1)))
        if len(duration_values) > 1:
            ctx.valid_slots_for_combined_group[group_id] = []
            continue
        block = next(iter(duration_values), 1)

        combined_allowed: set[Any] | None = None
        for sid in sec_ids:
            s_allowed = set(ctx.allowed_slots_by_section.get(sid, set()))
            combined_allowed = s_allowed if combined_allowed is None else (combined_allowed & s_allowed)
        if not combined_allowed:
            ctx.valid_slots_for_combined_group[group_id] = []
            continue

        teacher_blocked_cg: set[Any] = dallowed.get(assigned_teacher_id, set())
        if block <= 1:
            ctx.valid_slots_for_combined_group[group_id] = sorted(combined_allowed - teacher_blocked_cg)
        else:
            from solver.pre_solve_locks import contiguous_starts

            starts: list[Any] = []
            for day in range(6):
                day_indices = sorted(
                    int(ctx.slot_info[sid][1])
                    for sid in combined_allowed
                    if int(ctx.slot_info.get(sid, (-1, -1))[0]) == day and sid not in teacher_blocked_cg
                )
                if len(day_indices) < block:
                    continue
                for start_idx in contiguous_starts(day_indices, block):
                    ok = True
                    for j in range(block):
                        ts = ctx.slot_by_day_index.get((day, start_idx + j))
                        if ts is None or ts.id not in combined_allowed or ts.id in teacher_blocked_cg:
                            ok = False
                            break
                    if not ok:
                        continue
                    ts0 = ctx.slot_by_day_index.get((day, start_idx))
                    if ts0 is not None:
                        starts.append(ts0.id)
            ctx.valid_slots_for_combined_group[group_id] = starts

    # ── Elective-batch pruning ────────────────────────────────────────────
    # apply_pre_solve_locks() already called _ensure_elective_batches(), so
    # ctx.elective_batches_by_block is fully populated here.  Pre-compute
    # per-batch valid slot lists so _create_elective_block_vars does O(1)
    # lookups instead of recomputing intersections at model-build time.
    for block_id, sec_ids_in_block in ctx.sections_by_block.items():
        if not sec_ids_in_block:
            continue
        pairs = ctx.block_subject_pairs_by_block.get(block_id, [])
        if not pairs:
            continue
        eb_subj_objs = [ctx.subject_by_id.get(subj_id) for subj_id, _tid in pairs]
        eb_subj_objs = [s for s in eb_subj_objs if s is not None]
        if len(eb_subj_objs) != len(pairs):
            continue
        if any(str(s.subject_type) != "THEORY" for s in eb_subj_objs):
            continue

        duration_values = [max(1, int(ctx.duration_for(s.id) or 1)) for s in eb_subj_objs]
        if len(set(duration_values)) != 1:
            continue
        block = int(duration_values[0])

        eb_blocked: set[Any] = set()
        for _subj_id, teacher_id in pairs:
            eb_blocked.update(dallowed.get(teacher_id, set()))

        for batch_idx, batch_sec_ids in enumerate(ctx.elective_batches_by_block.get(block_id, [])):
            eb_allowed: set[Any] | None = None
            for sec_id in batch_sec_ids:
                s_allowed = set(ctx.allowed_slots_by_section.get(sec_id, set()))
                eb_allowed = s_allowed if eb_allowed is None else (eb_allowed & s_allowed)
            if not eb_allowed:
                ctx.valid_slots_for_elective_batch[(block_id, batch_idx)] = []
                continue

            if block <= 1:
                ctx.valid_slots_for_elective_batch[(block_id, batch_idx)] = sorted(eb_allowed - eb_blocked)
                continue

            from solver.pre_solve_locks import contiguous_starts

            starts: list[Any] = []
            for day in range(6):
                day_indices = sorted(
                    int(ctx.slot_info[sid][1])
                    for sid in eb_allowed
                    if int(ctx.slot_info.get(sid, (-1, -1))[0]) == day and sid not in eb_blocked
                )
                if len(day_indices) < block:
                    continue
                for start_idx in contiguous_starts(day_indices, block):
                    ok = True
                    for j in range(block):
                        ts = ctx.slot_by_day_index.get((day, start_idx + j))
                        if ts is None or ts.id not in eb_allowed or ts.id in eb_blocked:
                            ok = False
                            break
                    if not ok:
                        continue
                    ts0 = ctx.slot_by_day_index.get((day, start_idx))
                    if ts0 is not None:
                        starts.append(ts0.id)
            ctx.valid_slots_for_elective_batch[(block_id, batch_idx)] = starts


def _validate_domain_reduction(ctx: SolverContext) -> None:
    """Phase 7 Enhancement: Validate and report domain reduction effectiveness.
    
    Post-pruning checks:
      1. Warn if any (section, subject) pair has been pruned to 0 slots
         (indicates likely infeasibility — that subject can't be scheduled)
      2. Validate room type availability for subjects needing specific room types
      3. Validate subject allowed-rooms restrictions don't block all rooms
      4. Log domain reduction metrics to help diagnose solver congestion
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Check 1: Empty slot lists (infeasibility indicators)
    zero_slot_pairs = []
    for (sec_id, subj_id), slot_list in ctx.valid_slots_by_section_subject.items():
        if not slot_list:
            subject = ctx.subject_by_id.get(subj_id)
            section = ctx.section_by_id.get(sec_id)
            if subject and section:
                teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
                zero_slot_pairs.append({
                    "section": str(section.name or section.id),
                    "subject": str(subject.name or subject.id),
                    "teacher": str(ctx.teacher_by_id.get(teacher_id, "UNKNOWN") if teacher_id else "UNKNOWN"),
                    "track": str(getattr(section, "track", "CORE") or "CORE"),
                })
    
    if zero_slot_pairs:
        logger.warning(
            "[solver] DOMAIN_REDUCTION: %d (section,subject) pairs pruned to 0 slots — may cause infeasibility. "
            "First 5: %s",
            len(zero_slot_pairs),
            zero_slot_pairs[:5]
        )
    
    # Check 2: Room type availability for subjects
    lab_count = len(ctx.rooms_by_type.get("LAB", []))
    theory_count = len(ctx.rooms_by_type.get("CLASSROOM", [])) + len(ctx.rooms_by_type.get("LT", []))
    
    lab_subject_count = sum(
        1 for subj in ctx.subjects
        if str(getattr(subj, "subject_type", "THEORY")) == "LAB"
    )
    
    if lab_subject_count > 0 and lab_count == 0:
        logger.warning(
            "[solver] DOMAIN_REDUCTION: %d LAB subjects exist but no LAB rooms available — "
            "LAB subjects cannot be scheduled.",
            lab_subject_count
        )
    
    # Check 3: Allowed-rooms restrictions don't block all compatible rooms
    allowed_rooms_issues = []
    for subj_id, allowed_room_ids in ctx.allowed_rooms_by_subject.items():
        subject = ctx.subject_by_id.get(subj_id)
        if not subject or not allowed_room_ids:
            continue
        
        subj_type = str(getattr(subject, "subject_type", "THEORY"))
        allowed_rooms = [ctx.room_by_id.get(rid) for rid in allowed_room_ids]
        allowed_rooms = [r for r in allowed_rooms if r is not None]
        
        if not allowed_rooms:
            allowed_rooms_issues.append({
                "subject": str(subject.name or subject.id),
                "subject_type": subj_type,
                "reason": "all_allowed_rooms_not_found",
            })
        else:
            allowed_types = set(str(r.room_type) for r in allowed_rooms)
            required_types = {"LAB"} if subj_type == "LAB" else {"CLASSROOM", "LT"}
            if not (allowed_types & required_types):
                allowed_rooms_issues.append({
                    "subject": str(subject.name or subject.id),
                    "subject_type": subj_type,
                    "allowed_types": list(allowed_types),
                    "required_types": list(required_types),
                    "reason": "type_mismatch",
                })
    
    if allowed_rooms_issues:
        logger.warning(
            "[solver] DOMAIN_REDUCTION: %d subjects have invalid allowed-rooms restrictions. "
            "First 3: %s",
            len(allowed_rooms_issues),
            allowed_rooms_issues[:3]
        )
    
    # Check 4: Domain reduction metrics
    total_slots_available = sum(len(v) for v in ctx.valid_slots_by_section_subject.values())
    total_possible_slots = len(ctx.slots) * len(
        [(sec_id, subj_id) 
         for sec_id in ctx.section_by_id
         for subj_id, _ in ctx.section_required.get(sec_id, [])
         if ctx.subject_by_id.get(subj_id) is not None]
    )
    
    if total_possible_slots > 0:
        reduction_pct = 100 * (1 - total_slots_available / max(1, total_possible_slots))
        logger.info(
            "[solver] DOMAIN_REDUCTION: %.1f%% of slots pruned (%d → %d valid slots)",
            reduction_pct,
            total_possible_slots,
            total_slots_available,
        )
    
    # Store metrics in context for later retrieval
    if not hasattr(ctx, 'domain_reduction_metrics'):
        ctx.domain_reduction_metrics = {}
    ctx.domain_reduction_metrics.update({
        "zero_slot_pairs": len(zero_slot_pairs),
        "allowed_rooms_issues": len(allowed_rooms_issues),
        "total_slots_available": total_slots_available,
        "lab_rooms": lab_count,
        "theory_rooms": theory_count,
        "lab_subjects": lab_subject_count,
    })
    
    # Early termination check: If EVERY (section, subject) pair has 0 slots,
    # log critical error (indicates entire model is infeasible pre-solve)
    if ctx.valid_slots_by_section_subject and all(
        not v for v in ctx.valid_slots_by_section_subject.values()
    ):
        logger.critical(
            "[solver] DOMAIN_REDUCTION: CRITICAL — ALL (section,subject) pairs pruned to 0 slots. "
            "Model is certainly infeasible. Proceeding with warning."
        )

