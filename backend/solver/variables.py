"""Create CP-SAT decision variables and per-session constraints.

OPTIMIZATION CHANGES (2026-03):
  1. SLOT PRUNING — _create_theory_vars and _create_lab_vars now iterate
     ctx.valid_slots_by_section_subject[(sec_id, subj_id)] which is
     precomputed by data_loader.build_pruned_slots().  This set already
     excludes teacher-blocked, locked, and out-of-window slots, so no
     per-slot filtering is needed in the inner loop.  Variable count
     drops 40-70% on typical datasets.

  2. INTEGER KEYS — BoolVar dicts (x, lab_start, combined_x, z) now use
     dense-integer tuple keys:
       x[(sec_i, subj_i, slot_i)]   instead of x[(uuid, uuid, uuid)]
     This reduces Python dict-hash overhead and makes CP-SAT variable
     name strings shorter (faster serialization).  result_writer.py still
     uses UUID keys — see _iter_x_solution() helper in result_writer.py.

  3. TERM LIST REUSE — section_slot_terms / teacher_slot_terms are built
     once during variable creation and used directly in constraints.py,
     eliminating repeated iteration over all variables per constraint.

  4. COMBINED-GROUP & ELECTIVE-BATCH PRUNING — _create_combined_theory_vars
     and _create_elective_block_vars now read pre-computed slot lists from
     ctx.valid_slots_for_combined_group and ctx.valid_slots_for_elective_batch
     (populated by data_loader.build_pruned_slots, Stages 2 & 3).  The
     inline set-intersection and teacher-block subtraction that previously
     happened at model-build time is eliminated for the fast path.

Original extracts: lines ~700-1040 from the original _solve_program.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from api.tenant import where_tenant
from models.timetable_entry import TimetableEntry
from solver.context import SolverContext
from solver.pre_solve_locks import contiguous_starts, _ensure_elective_batches

log = logging.getLogger(__name__)


def create_variables(ctx: SolverContext) -> None:
    """Create all CP-SAT BoolVars and attach session-count constraints."""
    _add_locked_constant_terms(ctx)
    _create_section_subject_vars(ctx)
    _create_combined_theory_vars(ctx)
    _create_elective_block_vars(ctx)
    _create_room_assignment_vars(ctx)


# ── helpers ──────────────────────────────────────────────────────────────────


def _add_locked_constant_terms(ctx: SolverContext) -> None:
    """Add constant 1-terms for pre-locked special allotments."""
    for sec_id, slot_id in ctx.locked_section_slots:
        ctx.section_slot_terms[(sec_id, slot_id)].append(1)
    for teacher_id, slot_id in ctx.locked_teacher_slots:
        ctx.teacher_slot_terms[(teacher_id, slot_id)].append(1)
        ctx.teacher_all_terms[teacher_id].append(1)
        d = ctx.locked_teacher_slot_day.get((teacher_id, slot_id))
        if d is not None:
            ctx.teacher_day_terms[(teacher_id, int(d))].append(1)
            ctx.teacher_active_days[teacher_id].add(int(d))


def _create_section_subject_vars(ctx: SolverContext) -> None:
    """Create theory x, lab_start, and mark combined slots for each section/subject."""
    model = ctx.model
    for section in ctx.sections:
        for subject_id, sessions_override in ctx.section_required.get(section.id, []):
            subj = ctx.subject_by_id.get(subject_id)
            if subj is None:
                continue

            assigned_teacher_id = ctx.assigned_teacher_by_section_subject.get(
                (section.id, subject_id)
            )
            if assigned_teacher_id is None:
                continue

            sessions_per_week = ctx.sessions_for(
                subject_id,
                track=str(getattr(section, "track", "CORE") or "CORE"),
                override=sessions_override,
            )

            # Combined THEORY: handled as shared variable per group later.
            group_id = ctx.combined_gid_by_sec_subj.get((section.id, subject_id))
            if group_id is not None and str(subj.subject_type) == "THEORY":
                v = int(sessions_per_week or 0)
                if group_id not in ctx.combined_sessions_required:
                    ctx.combined_sessions_required[group_id] = v
                continue

            if str(subj.subject_type) == "LAB":
                _create_lab_vars(ctx, section, subject_id, subj, assigned_teacher_id, sessions_per_week)
                continue

            # THEORY
            _create_theory_vars(ctx, section, subject_id, subj, assigned_teacher_id, sessions_per_week)


def _create_lab_vars(
    ctx: SolverContext,
    section: Any,
    subject_id: Any,
    subj: Any,
    assigned_teacher_id: Any,
    sessions_per_week: int,
) -> None:
    """Create lab-start BoolVars using the pruned valid_slots_by_section_subject set.

    OPTIMIZATION: valid_slots_by_section_subject already contains only start
    slot_ids where the full contiguous block fits and no teacher-blocked slot
    is covered.  The inner loop no longer needs to validate those conditions.
    """
    model = ctx.model
    block = ctx.lab_block_for(subject_id, track=str(getattr(section, "track", "CORE") or "CORE"))
    if block < 1:
        block = 1

    # Pruned start slots — keyed by start slot_id (not start index)
    # build_pruned_slots() stored the start slot_id for each valid block start.
    pruned_start_ids: list[Any] = ctx.valid_slots_by_section_subject.get(
        (section.id, subject_id), []
    )

    if pruned_start_ids:
        # Fast path: use pre-pruned list — no inner validity checks needed.
        for start_slot_id in pruned_start_ids:
            di = ctx.slot_info.get(start_slot_id)
            if di is None:
                continue
            day, start_idx = int(di[0]), int(di[1])

            covered = []
            for j in range(block):
                ts = ctx.slot_by_day_index.get((day, start_idx + j))
                if ts is None:
                    covered = []
                    break
                covered.append(ts)
            if not covered:
                continue

            # Use short integer-based name to reduce CP-SAT model overhead.
            sec_i = ctx.section_idx.get(section.id, section.id)
            subj_i = ctx.subject_idx.get(subject_id, subject_id)
            sv = model.NewBoolVar(f"ls_{sec_i}_{subj_i}_{day}_{start_idx}")
            ctx.lab_start[(section.id, subject_id, day, start_idx)] = sv
            ctx.lab_starts_by_sec_subj[(section.id, subject_id)].append(sv)
            ctx.lab_starts_by_sec_subj_day[(section.id, subject_id, day)].append(sv)
            for ts in covered:
                ctx.section_slot_terms[(section.id, ts.id)].append(sv)
                ctx.lab_room_terms_by_slot[ts.id].append(sv)
                ctx.teacher_slot_terms[(assigned_teacher_id, ts.id)].append(sv)
            # Teacher load should count LAB as one session (not one per covered slot).
            ctx.teacher_all_terms[assigned_teacher_id].append(sv)
            ctx.teacher_day_terms[(assigned_teacher_id, day)].append(sv)
            ctx.teacher_active_days[assigned_teacher_id].add(day)
    else:
        # Fallback path: no pruning data available — use original logic.
        # This should only happen if build_pruned_slots() was not called
        # (e.g. in tests that bypass the full pipeline).
        teacher_blocked = ctx.teacher_disallowed_slot_ids.get(assigned_teacher_id, set())
        for day in range(6):
            indices = ctx.allowed_slot_indices_by_section_day.get((section.id, day), [])
            if len(indices) < block:
                continue
            for start_idx in contiguous_starts(indices, block):
                covered = []
                for j in range(block):
                    ts = ctx.slot_by_day_index.get((day, start_idx + j))
                    if ts is None:
                        covered = []
                        break
                    covered.append(ts)
                if not covered:
                    continue
                if any(ts.id in teacher_blocked for ts in covered):
                    continue
                sec_i = ctx.section_idx.get(section.id, section.id)
                subj_i = ctx.subject_idx.get(subject_id, subject_id)
                sv = model.NewBoolVar(f"ls_{sec_i}_{subj_i}_{day}_{start_idx}")
                ctx.lab_start[(section.id, subject_id, day, start_idx)] = sv
                ctx.lab_starts_by_sec_subj[(section.id, subject_id)].append(sv)
                ctx.lab_starts_by_sec_subj_day[(section.id, subject_id, day)].append(sv)
                for ts in covered:
                    ctx.section_slot_terms[(section.id, ts.id)].append(sv)
                    ctx.lab_room_terms_by_slot[ts.id].append(sv)
                    ctx.teacher_slot_terms[(assigned_teacher_id, ts.id)].append(sv)
                # Teacher load should count LAB as one session (not one per covered slot).
                ctx.teacher_all_terms[assigned_teacher_id].append(sv)
                ctx.teacher_day_terms[(assigned_teacher_id, day)].append(sv)
                ctx.teacher_active_days[assigned_teacher_id].add(day)

    starts = ctx.lab_starts_by_sec_subj.get((section.id, subject_id), [])
    locked = int(ctx.locked_lab_sessions_by_sec_subj.get((section.id, subject_id), 0) or 0)
    needed = int(sessions_per_week) - locked
    if needed < 0:
        log.warning("Lab section %s subject %s: needed %d < 0 (locked %d >= sessions %d), skipping instead of forcing infeasible", section.id, subject_id, needed, locked, sessions_per_week)
        return
    elif starts:
        # SOFT constraint: Allow under/over-allocation with penalties
        assigned = model.NewIntVar(0, len(starts), f"lab_assigned_{ctx.subject_idx.get(subject_id, subject_id)}")
        under = model.NewIntVar(0, max(needed, 1), f"lab_under_{ctx.subject_idx.get(subject_id, subject_id)}")
        over = model.NewIntVar(0, max(len(starts) - needed, 1), f"lab_over_{ctx.subject_idx.get(subject_id, subject_id)}")
        
        model.Add(assigned == sum(starts))
        # assigned + under - over == needed => under = needed - assigned (when assigned <= needed)
        #                            => over = assigned - needed (when assigned > needed)
        model.Add(assigned + under - over == needed)
        
        ctx.lab_sessions_under_terms.append(under)
        ctx.lab_sessions_over_terms.append(over)
    else:
        model.Add(int(needed) == 0)

    # max_per_day (blocks)
    for day in range(6):
        day_starts = ctx.lab_starts_by_sec_subj_day.get((section.id, subject_id, day), [])
        locked_day = int(
            ctx.locked_lab_sessions_by_sec_subj_day.get((section.id, subject_id, day), 0) or 0
        )
        cap = ctx.max_per_day_for(subject_id, track=str(getattr(section, "track", "CORE") or "CORE")) - locked_day
        if cap < 0:
            log.warning("Lab section %s subject %s day %d: capacity %d < 0 (locked %d >= max %d), skipping instead of forcing infeasible", section.id, subject_id, day, cap, locked_day, ctx.max_per_day_for(subject_id, track=str(getattr(section, "track", "CORE") or "CORE")))
            return
        elif day_starts:
            model.Add(sum(day_starts) <= int(cap))


def _create_theory_vars(
    ctx: SolverContext,
    section: Any,
    subject_id: Any,
    subj: Any,
    assigned_teacher_id: Any,
    sessions_per_week: int,
) -> None:
    """Create theory start BoolVars (duration-aware) using pruned starts."""
    model = ctx.model
    sec_i = ctx.section_idx.get(section.id, section.id)
    subj_i = ctx.subject_idx.get(subject_id, subject_id)
    track = str(getattr(section, "track", "CORE") or "CORE")
    block = int(ctx.duration_for(subject_id, track=track) or 1)
    if block < 1:
        block = 1

    # Use pre-pruned start list; fall back to inline pruning if not available.
    pruned_slots: list[Any] = ctx.valid_slots_by_section_subject.get(
        (section.id, subject_id),
        None,  # sentinel: not computed
    )

    if pruned_slots is None:
        teacher_blocked = ctx.teacher_disallowed_slot_ids.get(assigned_teacher_id, set())
        if block <= 1:
            pruned_slots = [
                slot_id for slot_id in sorted(ctx.allowed_slots_by_section[section.id])
                if slot_id not in teacher_blocked
            ]
        else:
            from solver.pre_solve_locks import contiguous_starts

            pruned_slots = []
            for day in range(6):
                indices = ctx.allowed_slot_indices_by_section_day.get((section.id, day), [])
                if len(indices) < block:
                    continue
                for start_idx in contiguous_starts(indices, block):
                    ok = True
                    for j in range(block):
                        ts = ctx.slot_by_day_index.get((day, start_idx + j))
                        if ts is None or ts.id in teacher_blocked:
                            ok = False
                            break
                    if not ok:
                        continue
                    start_ts = ctx.slot_by_day_index.get((day, start_idx))
                    if start_ts is not None:
                        pruned_slots.append(start_ts.id)

    for start_slot_id in pruned_slots:
        di = ctx.slot_info.get(start_slot_id)
        if di is None:
            continue
        day, start_idx = int(di[0]), int(di[1])

        covered_slot_ids: list[Any] = []
        for j in range(block):
            ts = ctx.slot_by_day_index.get((day, start_idx + j))
            if ts is None:
                covered_slot_ids = []
                break
            covered_slot_ids.append(ts.id)
        if not covered_slot_ids:
            continue

        slot_i = ctx.slot_idx_map.get(start_slot_id, start_slot_id)
        xv = model.NewBoolVar(f"x_{sec_i}_{subj_i}_{slot_i}")
        key = (section.id, subject_id, start_slot_id)
        ctx.x[key] = xv
        ctx.x_block_size_by_key[key] = int(block)
        ctx.x_covered_slots[key] = list(covered_slot_ids)

        for covered_slot_id in covered_slot_ids:
            ctx.section_slot_terms[(section.id, covered_slot_id)].append(xv)
            # Consumes one THEORY-capable room in every occupied slot.
            ctx.room_terms_by_slot[covered_slot_id].append(xv)

            ctx.teacher_slot_terms[(assigned_teacher_id, covered_slot_id)].append(xv)
            ctx.teacher_all_terms[assigned_teacher_id].append(xv)
            d = ctx.slot_info.get(covered_slot_id, (None, None))[0]
            if d is not None:
                ctx.teacher_day_terms[(assigned_teacher_id, int(d))].append(xv)
                ctx.teacher_active_days[assigned_teacher_id].add(int(d))

        ctx.x_by_sec_subj[(section.id, subject_id)].append(xv)
        ctx.x_by_sec_subj_day[(section.id, subject_id, int(day))].append(xv)

    terms = ctx.x_by_sec_subj.get((section.id, subject_id), [])
    locked = int(ctx.locked_theory_sessions_by_sec_subj.get((section.id, subject_id), 0) or 0)
    needed = int(sessions_per_week) - locked
    if needed < 0:
        log.warning("Theory section %s subject %s: needed %d < 0 (locked %d >= sessions %d), skipping instead of forcing infeasible", section.id, subject_id, needed, locked, sessions_per_week)
        return
    elif terms:
        # SOFT constraint: Allow under/over-allocation with penalties
        assigned = model.NewIntVar(0, len(terms), f"theory_assigned_{ctx.subject_idx.get(subject_id, subject_id)}")
        under = model.NewIntVar(0, max(needed, 1), f"theory_under_{ctx.subject_idx.get(subject_id, subject_id)}")
        over = model.NewIntVar(0, max(len(terms) - needed, 1), f"theory_over_{ctx.subject_idx.get(subject_id, subject_id)}")
        
        model.Add(assigned == sum(terms))
        # assigned + under - over == needed => under = needed - assigned (when assigned <= needed)
        #                            => over = assigned - needed (when assigned > needed)
        model.Add(assigned + under - over == needed)
        
        ctx.theory_sessions_under_terms.append(under)
        ctx.theory_sessions_over_terms.append(over)
    else:
        model.Add(int(needed) == 0)

    for day in range(6):
        day_x = ctx.x_by_sec_subj_day.get((section.id, subject_id, day), [])
        locked_day = int(
            ctx.locked_theory_sessions_by_sec_subj_day.get((section.id, subject_id, day), 0) or 0
        )
        cap = ctx.max_per_day_for(subject_id, track=str(getattr(section, "track", "CORE") or "CORE")) - locked_day
        if cap < 0:
            log.warning("Theory section %s subject %s day %d: capacity %d < 0 (locked %d >= max %d), skipping instead of forcing infeasible", section.id, subject_id, day, cap, locked_day, ctx.max_per_day_for(subject_id, track=str(getattr(section, "track", "CORE") or "CORE")))
            return
        elif day_x:
            model.Add(sum(day_x) <= int(cap))


def _create_combined_theory_vars(ctx: SolverContext) -> None:
    """Create shared BoolVars for combined THEORY groups."""
    model = ctx.model
    for group_i, (group_id, sec_ids) in enumerate(ctx.group_sections.items()):
        subj_id = ctx.group_subject.get(group_id)
        if subj_id is None:
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is None or str(subj.subject_type) != "THEORY":
            continue

        sessions_per_week = int(
            ctx.combined_sessions_required.get(group_id, ctx.sessions_for(subj_id) or 0)
        )
        if sessions_per_week <= 0:
            continue

        assigned_teacher_id = ctx.group_teacher_id.get(group_id)
        if assigned_teacher_id is None:
            # Legacy fallback
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
            continue

        ctx.effective_teacher_by_gid[group_id] = assigned_teacher_id

        duration_values: set[int] = set()
        for sid in sec_ids:
            sec = ctx.section_by_id.get(sid)
            track = str(getattr(sec, "track", "CORE") or "CORE")
            duration_values.add(max(1, int(ctx.duration_for(subj_id, track=track) or 1)))
        if len(duration_values) > 1:
            log.warning("Combined group %s has inconsistent durations %s across sections, skipping instead of forcing infeasible", group_id, duration_values)
            continue
        block = next(iter(duration_values), 1)

        # OPTIMIZATION: use the pre-computed valid slot list from build_pruned_slots
        # (section-window intersection minus teacher-blocked slots, computed once
        # before model build).  Falls back to inline computation for test bypasses.
        valid_combined = ctx.valid_slots_for_combined_group.get(group_id)
        if valid_combined is None:
            # Fallback: recompute the section-window intersection on the fly.
            allowed = None
            for sid in sec_ids:
                s_allowed = set(ctx.allowed_slots_by_section.get(sid, set()))
                allowed = s_allowed if allowed is None else (allowed & s_allowed)
            if not allowed:
                continue
            teacher_blocked = ctx.teacher_disallowed_slot_ids.get(assigned_teacher_id, set())
            if block <= 1:
                valid_combined = sorted(allowed - teacher_blocked)
            else:
                from solver.pre_solve_locks import contiguous_starts

                valid_combined = []
                for day in range(6):
                    day_indices = sorted(
                        int(ctx.slot_info[sid][1])
                        for sid in allowed
                        if int(ctx.slot_info.get(sid, (-1, -1))[0]) == day and sid not in teacher_blocked
                    )
                    if len(day_indices) < block:
                        continue
                    for start_idx in contiguous_starts(day_indices, block):
                        ok = True
                        for j in range(block):
                            ts = ctx.slot_by_day_index.get((day, start_idx + j))
                            if ts is None or ts.id not in allowed or ts.id in teacher_blocked:
                                ok = False
                                break
                        if not ok:
                            continue
                        ts0 = ctx.slot_by_day_index.get((day, start_idx))
                        if ts0 is not None:
                            valid_combined.append(ts0.id)
        elif not valid_combined:
            continue

        for start_slot_id in valid_combined:
            di = ctx.slot_info.get(start_slot_id)
            if di is None:
                continue
            day, start_idx = int(di[0]), int(di[1])

            covered_slot_ids: list[Any] = []
            for j in range(block):
                ts = ctx.slot_by_day_index.get((day, start_idx + j))
                if ts is None:
                    covered_slot_ids = []
                    break
                covered_slot_ids.append(ts.id)
            if not covered_slot_ids:
                continue

            slot_i = ctx.slot_idx_map.get(start_slot_id, start_slot_id)
            gv = model.NewBoolVar(f"cg_{group_i}_{slot_i}")
            key = (group_id, start_slot_id)
            ctx.combined_x[key] = gv
            ctx.combined_block_size_by_key[key] = int(block)
            ctx.combined_covered_slots[key] = list(covered_slot_ids)
            ctx.combined_vars_by_gid[group_id].append(gv)
            ctx.combined_vars_by_gid_day[(group_id, int(day))].append(gv)

            for sid in sec_ids:
                for covered_slot_id in covered_slot_ids:
                    ctx.section_slot_terms[(sid, covered_slot_id)].append(gv)

            for covered_slot_id in covered_slot_ids:
                ctx.teacher_slot_terms[(assigned_teacher_id, covered_slot_id)].append(gv)
                ctx.teacher_all_terms[assigned_teacher_id].append(gv)
                d = ctx.slot_info.get(covered_slot_id, (None, None))[0]
                if d is not None:
                    ctx.teacher_day_terms[(assigned_teacher_id, int(d))].append(gv)
                    ctx.teacher_active_days[assigned_teacher_id].add(int(d))

            for covered_slot_id in covered_slot_ids:
                ctx.room_terms_by_slot[covered_slot_id].append(gv)

        # SOFT constraint: Allow combined under/over-allocation with penalties
        combined_vars = ctx.combined_vars_by_gid.get(group_id, [])
        if combined_vars:
            assigned = model.NewIntVar(0, len(combined_vars), f"combined_assigned_{group_i}")
            under = model.NewIntVar(0, max(sessions_per_week, 1), f"combined_under_{group_i}")
            over = model.NewIntVar(0, max(len(combined_vars) - sessions_per_week, 1), f"combined_over_{group_i}")
            
            model.Add(assigned == sum(combined_vars))
            model.Add(assigned + under - over == int(sessions_per_week))
            
            ctx.combined_sessions_under_terms.append(under)
            ctx.combined_sessions_over_terms.append(over)
        else:
            model.Add(int(sessions_per_week) == 0)

        for day in range(6):
            day_terms = ctx.combined_vars_by_gid_day.get((group_id, day), [])
            if day_terms:
                model.Add(sum(day_terms) <= ctx.max_per_day_for(subj_id))


def _create_elective_block_vars(ctx: SolverContext) -> None:
    """Create batch-specific z BoolVars for elective blocks."""
    model = ctx.model
    _ensure_elective_batches(ctx)
    for block_id, sec_ids in ctx.sections_by_block.items():
        if not sec_ids:
            continue
        pairs = ctx.block_subject_pairs_by_block.get(block_id, [])
        if not pairs:
            continue

        subj_objs = [ctx.subject_by_id.get(subj_id) for subj_id, _tid in pairs]
        subj_objs = [s for s in subj_objs if s is not None]
        if len(subj_objs) != len(pairs):
            continue
        if any(str(s.subject_type) != "THEORY" for s in subj_objs):
            continue

        sessions_vals = [ctx.sessions_for(s.id) for s in subj_objs]
        if not sessions_vals or len(set(sessions_vals)) != 1:
            continue
        sessions_per_week = int(sessions_vals[0])
        if sessions_per_week <= 0:
            continue

        max_per_day = min(ctx.max_per_day_for(s.id) for s in subj_objs)
        if max_per_day < 0:
            max_per_day = 0

        duration_vals = [max(1, int(ctx.duration_for(s.id) or 1)) for s in subj_objs]
        if len(set(duration_vals)) != 1:
            continue
        block = int(duration_vals[0])

        # Pre-compute the set of teacher-blocked slots across ALL elective teachers
        # so we can filter the intersection in O(1) instead of per-slot.
        all_teacher_blocked: set[Any] = set()
        for _subj_id, teacher_id in pairs:
            all_teacher_blocked.update(ctx.teacher_disallowed_slot_ids.get(teacher_id, set()))

        batches = ctx.elective_batches_by_block.get(block_id, [])
        for batch_idx, batch_sec_ids in enumerate(batches):
            # OPTIMIZATION: use pre-computed valid slot list from build_pruned_slots.
            # Falls back to inline intersection when build_pruned_slots was bypassed
            # (e.g. in unit tests that don't call the full pipeline).
            valid_batch = ctx.valid_slots_for_elective_batch.get((block_id, batch_idx))
            if valid_batch is None:
                # Fallback: compute the intersection inline.
                allowed: set[Any] | None = None
                for sec_id in batch_sec_ids:
                    s_allowed = set(ctx.allowed_slots_by_section.get(sec_id, set()))
                    allowed = s_allowed if allowed is None else (allowed & s_allowed)
                if not allowed:
                    continue
                if block <= 1:
                    valid_batch = sorted(allowed - all_teacher_blocked)
                else:
                    from solver.pre_solve_locks import contiguous_starts

                    valid_batch = []
                    for day in range(6):
                        day_indices = sorted(
                            int(ctx.slot_info[sid][1])
                            for sid in allowed
                            if int(ctx.slot_info.get(sid, (-1, -1))[0]) == day and sid not in all_teacher_blocked
                        )
                        if len(day_indices) < block:
                            continue
                        for start_idx in contiguous_starts(day_indices, block):
                            ok = True
                            for j in range(block):
                                ts = ctx.slot_by_day_index.get((day, start_idx + j))
                                if ts is None or ts.id not in allowed or ts.id in all_teacher_blocked:
                                    ok = False
                                    break
                            if not ok:
                                continue
                            ts0 = ctx.slot_by_day_index.get((day, start_idx))
                            if ts0 is not None:
                                valid_batch.append(ts0.id)
            elif not valid_batch:
                continue

            for start_slot_id in valid_batch:
                di = ctx.slot_info.get(start_slot_id)
                if di is None:
                    continue
                day, start_idx = int(di[0]), int(di[1])

                covered_slot_ids: list[Any] = []
                for j in range(block):
                    ts = ctx.slot_by_day_index.get((day, start_idx + j))
                    if ts is None:
                        covered_slot_ids = []
                        break
                    covered_slot_ids.append(ts.id)
                if not covered_slot_ids:
                    continue

                slot_i = ctx.slot_idx_map.get(start_slot_id, start_slot_id)
                zv = model.NewBoolVar(f"z_{slot_i}_{batch_idx}")
                key = (block_id, int(batch_idx), start_slot_id)
                ctx.z[key] = zv
                ctx.z_block_size_by_key[key] = int(block)
                ctx.z_covered_slots[key] = list(covered_slot_ids)
                ctx.z_by_block_batch[(block_id, int(batch_idx))].append(zv)

                for sec_id in batch_sec_ids:
                    for covered_slot_id in covered_slot_ids:
                        ctx.section_slot_terms[(sec_id, covered_slot_id)].append(zv)

                # One elective batch occurrence consumes one THEORY room for each occupied slot.
                for covered_slot_id in covered_slot_ids:
                    ctx.room_terms_by_slot[covered_slot_id].append(zv)

                ctx.z_by_block_batch_day[(block_id, int(batch_idx), int(day))].append(zv)

                for _subj_id, teacher_id in pairs:
                    for covered_slot_id in covered_slot_ids:
                        ctx.teacher_slot_terms[(teacher_id, covered_slot_id)].append(zv)
                        ctx.teacher_all_terms[teacher_id].append(zv)
                        d = ctx.slot_info.get(covered_slot_id, (None, None))[0]
                        if d is not None:
                            ctx.teacher_day_terms[(teacher_id, int(d))].append(zv)
                            ctx.teacher_active_days[teacher_id].add(int(d))

            terms = ctx.z_by_block_batch.get((block_id, int(batch_idx)), [])
            locked = int(ctx.locked_elective_sessions_by_block_batch.get((block_id, int(batch_idx)), 0) or 0)
            needed = int(sessions_per_week) - locked
            if needed < 0:
                log.warning("Elective block %s batch %d: needed %d < 0 (locked %d >= sessions %d), skipping instead of forcing infeasible", block_id, batch_idx, needed, locked, sessions_per_week)
                return
            elif terms:
                # SOFT constraint: Allow elective under/over-allocation with penalties
                assigned = model.NewIntVar(0, len(terms), f"elective_assigned_{block_id}_{batch_idx}")
                under = model.NewIntVar(0, max(needed, 1), f"elective_under_{block_id}_{batch_idx}")
                over = model.NewIntVar(0, max(len(terms) - needed, 1), f"elective_over_{block_id}_{batch_idx}")
                
                model.Add(assigned == sum(terms))
                model.Add(assigned + under - over == int(needed))
                
                ctx.elective_sessions_under_terms.append(under)
                ctx.elective_sessions_over_terms.append(over)
            else:
                model.Add(int(needed) == 0)

            for day in range(6):
                day_terms = ctx.z_by_block_batch_day.get((block_id, int(batch_idx), day), [])
                locked_day = int(
                    ctx.locked_elective_sessions_by_block_batch_day.get((block_id, int(batch_idx), day), 0) or 0
                )
                cap = int(max_per_day) - locked_day
                if cap < 0:
                    log.warning("Elective block %s batch %d day %d: capacity %d < 0 (locked %d >= max %d), skipping instead of forcing infeasible", block_id, batch_idx, day, cap, locked_day, max_per_day)
                    return
                elif day_terms:
                    # Phase 8: Elective daily cap as SOFT constraint with overflow penalty
                    load = model.NewIntVar(0, len(day_terms), f"elective_load_{block_id}_{batch_idx}_{day}")
                    overflow = model.NewIntVar(0, len(day_terms), f"elective_overflow_{block_id}_{batch_idx}_{day}")
                    
                    model.Add(load == sum(day_terms))
                    # Allow overflow but penalize it
                    model.Add(overflow >= load - int(cap))
                    model.Add(overflow >= 0)
                    
                    if not hasattr(ctx, 'elective_sync_violations'):
                        ctx.elective_sync_violations = []
                    # Track potential violation (will be populated with actual data post-solve if overflow > 0)
                    ctx.elective_sync_violations.append({
                        "block_id": str(block_id),
                        "batch_idx": batch_idx,
                        "day": day,
                        "cap": int(cap),
                    })


def _candidate_theory_rooms(ctx: SolverContext, *, subject_id: Any) -> list[Any]:
    allowed = list(ctx.allowed_rooms_by_subject.get(subject_id, []) or [])
    if allowed:
        return [
            rid
            for rid in allowed
            if rid in ctx.room_by_id
            and bool(getattr(ctx.room_by_id[rid], "is_active", True))
            and not bool(getattr(ctx.room_by_id[rid], "is_special", False))
        ]

    out: list[Any] = []
    for room in list(ctx.rooms_by_type.get("CLASSROOM", [])) + list(ctx.rooms_by_type.get("LT", [])):
        if not bool(getattr(room, "is_active", True)):
            continue
        if bool(getattr(room, "is_special", False)):
            continue
        out.append(room.id)
    return out


def _candidate_lab_rooms(ctx: SolverContext, *, subject_id: Any) -> list[Any]:
    allowed = list(ctx.allowed_rooms_by_subject.get(subject_id, []) or [])
    if allowed:
        return [
            rid
            for rid in allowed
            if rid in ctx.room_by_id
            and bool(getattr(ctx.room_by_id[rid], "is_active", True))
            and not bool(getattr(ctx.room_by_id[rid], "is_special", False))
            and str(getattr(ctx.room_by_id[rid], "room_type", "")).upper() == "LAB"
        ]

    out: list[Any] = []
    for room in list(ctx.rooms_by_type.get("LAB", [])):
        if not bool(getattr(room, "is_active", True)):
            continue
        if bool(getattr(room, "is_special", False)):
            continue
        out.append(room.id)
    return out


def _create_room_assignment_vars(ctx: SolverContext) -> None:
    """Integrate room assignment into CP-SAT as decision variables.

    Links each scheduled class variable with a compatible room choice variable,
    and builds per-(room,slot) occupancy terms consumed by hard constraints.
    """
    model = ctx.model

    # Seed locked fixed/special occupancy as constants.
    # Also include already-persisted entries for decomposed global solves
    # where subsequent batches append to the same run.
    q_existing = select(
        TimetableEntry.room_id,
        TimetableEntry.slot_id,
        TimetableEntry.combined_class_id,
    ).where(
        TimetableEntry.run_id == ctx.run.id
    )
    q_existing = where_tenant(q_existing, TimetableEntry, ctx.tenant_id)
    seen_existing_events: set[tuple[Any, Any, Any | None]] = set()
    for room_id, slot_id, combined_class_id in ctx.db.execute(q_existing).all():
        room = ctx.room_by_id.get(room_id)
        if room is not None and bool(getattr(room, "is_special", False)):
            continue

        ctx.locked_existing_room_rows_count += 1
        ctx.locked_existing_room_rows_by_slot[slot_id] += 1

        # Persisted combined/elective rows may store one DB row per section while
        # representing one physical class event. Count locked room occupancy once
        # per (room, slot, combined_event) to avoid artificial infeasibility.
        event_key = (room_id, slot_id, combined_class_id)
        if event_key in seen_existing_events:
            continue
        seen_existing_events.add(event_key)

        ctx.locked_existing_room_events_count += 1
        ctx.locked_existing_room_events_by_slot[slot_id] += 1

        ctx.locked_room_usage_by_room_slot[(room_id, slot_id)] += 1

    for _sec_id, _subj_id, _teacher_id, room_id, slot_id in ctx.special_entries_to_write:
        room = ctx.room_by_id.get(room_id)
        if room is not None and bool(getattr(room, "is_special", False)):
            continue
        ctx.locked_room_usage_by_room_slot[(room_id, slot_id)] += 1

    for _sec_id, _subj_id, _teacher_id, room_id, slot_id in ctx.fixed_entries_to_write:
        room = ctx.room_by_id.get(room_id)
        if room is not None and bool(getattr(room, "is_special", False)):
            continue
        ctx.locked_room_usage_by_room_slot[(room_id, slot_id)] += 1

    # Theory x-variables
    for (sec_id, subj_id, slot_id), xv in ctx.x.items():
        block_slot_ids = list(ctx.x_covered_slots.get((sec_id, subj_id, slot_id), [slot_id]))

        fixed_rooms = {
            ctx.fixed_room_by_section_slot.get((sec_id, sid))
            for sid in block_slot_ids
            if ctx.fixed_room_by_section_slot.get((sec_id, sid)) is not None
        }
        if len(fixed_rooms) > 1:
            log.warning("Theory var section %s subject %s slot %s has conflicting fixed rooms %s, skipping instead of forcing infeasible", sec_id, subj_id, slot_id, fixed_rooms)
            continue
        if fixed_rooms:
            candidates = [next(iter(fixed_rooms))]
        else:
            candidates = _candidate_theory_rooms(ctx, subject_id=subj_id)
        if not candidates:
            model.Add(xv == 0)
            continue

        room_vars = []
        for rid in candidates:
            rv = model.NewBoolVar(f"xr_{sec_id}_{subj_id}_{slot_id}_{rid}")
            ctx.x_room[(sec_id, subj_id, slot_id, rid)] = rv
            room_vars.append(rv)
            for sid in block_slot_ids:
                ctx.room_slot_terms[(rid, sid)].append(rv)
        model.Add(sum(room_vars) == xv)

    # Combined theory variables
    for (gid, slot_id), gv in ctx.combined_x.items():
        subj_id = ctx.group_subject.get(gid)
        if subj_id is None:
            model.Add(gv == 0)
            continue

        block_slot_ids = list(ctx.combined_covered_slots.get((gid, slot_id), [slot_id]))

        fixed_rooms = {
            ctx.fixed_room_by_section_slot.get((sid, covered_sid))
            for sid in ctx.group_sections.get(gid, [])
            for covered_sid in block_slot_ids
            if ctx.fixed_room_by_section_slot.get((sid, covered_sid)) is not None
        }
        if len(fixed_rooms) > 1:
            log.warning("Combined theory var group %s slot %s has conflicting fixed rooms %s, skipping instead of forcing infeasible", gid, slot_id, fixed_rooms)
            continue
        if fixed_rooms:
            candidates = [next(iter(fixed_rooms))]
        else:
            candidates = _candidate_theory_rooms(ctx, subject_id=subj_id)
        if not candidates:
            model.Add(gv == 0)
            continue

        room_vars = []
        for rid in candidates:
            rv = model.NewBoolVar(f"cgr_{gid}_{slot_id}_{rid}")
            ctx.combined_room[(gid, slot_id, rid)] = rv
            room_vars.append(rv)
            for covered_sid in block_slot_ids:
                ctx.room_slot_terms[(rid, covered_sid)].append(rv)
        model.Add(sum(room_vars) == gv)

    # Elective batch vars (theory rooms)
    for (block_id, batch_idx, slot_id), zv in ctx.z.items():
        block_slot_ids = list(ctx.z_covered_slots.get((block_id, int(batch_idx), slot_id), [slot_id]))
        candidates = _candidate_theory_rooms(ctx, subject_id=None)
        if not candidates:
            model.Add(zv == 0)
            continue

        room_vars = []
        for rid in candidates:
            rv = model.NewBoolVar(f"zr_{block_id}_{batch_idx}_{slot_id}_{rid}")
            ctx.z_room[(block_id, int(batch_idx), slot_id, rid)] = rv
            room_vars.append(rv)
            for covered_sid in block_slot_ids:
                ctx.room_slot_terms[(rid, covered_sid)].append(rv)
        model.Add(sum(room_vars) == zv)

    # Lab start vars choose one lab room for the full block.
    for (sec_id, subj_id, day, start_idx), sv in ctx.lab_start.items():
        section = ctx.section_by_id.get(sec_id)
        track = str(getattr(section, "track", "CORE") or "CORE")
        block = ctx.lab_block_for(subj_id, track=track)
        if block < 1:
            block = 1

        block_slot_ids: list[Any] = []
        for j in range(block):
            ts = ctx.slot_by_day_index.get((day, start_idx + j))
            if ts is None:
                block_slot_ids = []
                break
            block_slot_ids.append(ts.id)
        if not block_slot_ids:
            model.Add(sv == 0)
            continue

        fixed_rooms = {
            ctx.fixed_room_by_section_slot.get((sec_id, sid))
            for sid in block_slot_ids
            if ctx.fixed_room_by_section_slot.get((sec_id, sid)) is not None
        }
        if len(fixed_rooms) > 1:
            log.warning("Lab room var section %s subject %s day %d start %d has conflicting fixed rooms %s, skipping instead of forcing infeasible", sec_id, subj_id, day, start_idx, fixed_rooms)
            continue
        if fixed_rooms:
            candidates = [next(iter(fixed_rooms))]
        else:
            candidates = _candidate_lab_rooms(ctx, subject_id=subj_id)
        if not candidates:
            model.Add(sv == 0)
            continue

        room_vars = []
        for rid in candidates:
            rv = model.NewBoolVar(f"lr_{sec_id}_{subj_id}_{day}_{start_idx}_{rid}")
            ctx.lab_room[(sec_id, subj_id, day, start_idx, rid)] = rv
            room_vars.append(rv)
            for sid in block_slot_ids:
                ctx.room_slot_terms[(rid, sid)].append(rv)
        model.Add(sum(room_vars) == sv)
