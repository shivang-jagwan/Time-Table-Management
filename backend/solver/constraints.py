"""Add hard and soft constraints to the CP-SAT model.

Extracts lines ~1040-1345 from the original _solve_program:
- Room capacity constraints (theory + lab)
- Fixed-entry hard constraints (force vars to 1)
- Section no-overlap (≤1 per slot)
- Section compactness (max gap + soft gap penalty)
- Teacher no-overlap
- Teacher weekly off day
- Teacher workload soft penalties (weekly/day/consecutive/preferred-slot)

PHASE 11 (2026-03): Flexible Slot Capacity
- REMOVED hard slot cap: model.Add(load <= total_appropriate_rooms)
- ADDED soft slot capacity overflow: allows overflow but penalizes
- ADDED quadratic load balancing: penalizes concentration of classes in single slot
- Classes can distribute across multiple time slots naturally
- Overflow penalty encourages (but doesn't force) spreading across available slots
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

from solver.context import SolverContext

log = logging.getLogger(__name__)


def add_constraints(ctx: SolverContext) -> None:
    """Add all constraints to ``ctx.model``."""

    _add_room_capacity_constraints(ctx)
    _add_fixed_entry_hard_constraints(ctx)
    _add_section_no_overlap(ctx)
    _add_combined_group_selection(ctx)
    _add_section_compactness(ctx)
    _add_subject_day_spread(ctx)
    _add_no_consecutive_same_subject(ctx)
    _add_lunch_break_constraint(ctx)
    _add_teacher_no_overlap(ctx)
    _add_room_slot_uniqueness(ctx)

    _add_teacher_weekly_off(ctx)
    _add_teacher_workload_soft_penalties(ctx)
    _add_teacher_compactness(ctx)
    _add_daily_load_balance(ctx)
    _add_slot_load_constraints(ctx)
    _add_section_max_daily_slots(ctx)
    _add_lab_day_continuity_preference(ctx)


# ── Room capacity ───────────────────────────────────────────────────────────


def _add_room_capacity_constraints(ctx: SolverContext) -> None:
    """Room capacity handling: SOFT penalties instead of hard limits.
    
    Phase 6 Stabilization: Convert from hard capacity cap to soft penalty.
    If a slot demands more rooms than available, allow it but penalize in objective.
    This ensures the solver never blocks due to room shortage.
    """
    model = ctx.model
    theory_room_capacity = len(ctx.rooms_by_type.get("CLASSROOM", [])) + len(
        ctx.rooms_by_type.get("LT", [])
    )
    lab_room_capacity = len(ctx.rooms_by_type.get("LAB", []))

    # Count pre-locked special and fixed entry room demand per slot.
    for _sec_id, subj_id, _teacher_id, _room_id, slot_id in ctx.special_entries_to_write:
        room = ctx.room_by_id.get(_room_id)
        if room is not None and bool(getattr(room, "is_special", False)):
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is not None and str(subj.subject_type) == "LAB":
            ctx.special_lab_by_slot[slot_id] += 1
        else:
            ctx.special_theory_by_slot[slot_id] += 1

    for _sec_id, subj_id, _teacher_id, _room_id, slot_id in ctx.fixed_entries_to_write:
        room = ctx.room_by_id.get(_room_id)
        if room is not None and bool(getattr(room, "is_special", False)):
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is not None and str(subj.subject_type) == "LAB":
            ctx.fixed_lab_by_slot[slot_id] += 1
        else:
            ctx.fixed_theory_by_slot[slot_id] += 1

    # SOFT: Theory room capacity with penalty overflow variable
    for ts in ctx.slots:
        slot_id = ts.id
        theory_load = (
            sum(ctx.room_terms_by_slot.get(slot_id, []))
            + int(ctx.special_theory_by_slot.get(slot_id, 0))
            + int(ctx.fixed_theory_by_slot.get(slot_id, 0))
            + int(ctx.locked_block_theory_room_demand_by_slot.get(slot_id, 0))
        )
        
        # Create overflow variable (soft penalty)
        theory_over = model.NewIntVar(0, 100, f"theory_room_over_{slot_id}")
        # Overflow is max(0, load - capacity)
        model.Add(theory_over >= theory_load - int(theory_room_capacity))
        model.Add(theory_over >= 0)
        ctx.theory_room_overflow_terms.append(theory_over)
    
    # SOFT: Lab room capacity with penalty overflow variable
    for ts in ctx.slots:
        slot_id = ts.id
        lab_load = (
            sum(ctx.lab_room_terms_by_slot.get(slot_id, []))
            + int(ctx.special_lab_by_slot.get(slot_id, 0))
            + int(ctx.fixed_lab_by_slot.get(slot_id, 0))
        )
        
        # Create overflow variable (soft penalty)
        lab_over = model.NewIntVar(0, 100, f"lab_room_over_{slot_id}")
        # Overflow is max(0, load - capacity)
        model.Add(lab_over >= lab_load - int(lab_room_capacity))
        model.Add(lab_over >= 0)
        ctx.lab_room_overflow_terms.append(lab_over)


def _add_room_slot_uniqueness(ctx: SolverContext) -> None:
    """Hard constraint: a room can host at most one class per slot."""
    for (room_id, slot_id), terms in ctx.room_slot_terms.items():
        if not terms:
            continue
        locked = int(ctx.locked_room_usage_by_room_slot.get((room_id, slot_id), 0) or 0)
        total_terms = list(terms)
        if locked > 0:
            ctx.model.Add(cp_model.LinearExpr.Sum(total_terms) <= (1 - locked))
        else:
            ctx.model.Add(cp_model.LinearExpr.Sum(total_terms) <= 1)


def _add_slot_load_constraints(ctx: SolverContext) -> None:
    """Slot load constraints with selectable room-balance policy.

    Modes:
      - ``soft``   : allow overflow and penalize it (default)
      - ``strict`` : enforce hard room-capacity per slot
    """
    model = ctx.model
    room_balance_mode = str(getattr(ctx, "room_balance_mode", "soft") or "soft").strip().lower()
    strict_room_cap = room_balance_mode == "strict"

    total_available_rooms = int(
        sum(
            1
            for room in ctx.rooms_all
            if bool(getattr(room, "is_active", True)) and not bool(getattr(room, "is_special", False))
        )
    )
    if total_available_rooms <= 0:
        return

    slot_load_vars = []
    max_slot_load = max(0, total_available_rooms)
    soft_threshold = max(1, int((total_available_rooms * 85 + 99) // 100))

    for ts in ctx.slots:
        slot_id = ts.id
        load = model.NewIntVar(0, max_slot_load * 2, f"slot_load_{slot_id}")  # Allow overflow beyond room count
        load_terms = list(ctx.room_terms_by_slot.get(slot_id, [])) + list(ctx.lab_room_terms_by_slot.get(slot_id, []))
        load_terms.append(int(ctx.special_theory_by_slot.get(slot_id, 0) or 0))
        load_terms.append(int(ctx.fixed_theory_by_slot.get(slot_id, 0) or 0))
        load_terms.append(int(ctx.locked_block_theory_room_demand_by_slot.get(slot_id, 0) or 0))
        load_terms.append(int(ctx.special_lab_by_slot.get(slot_id, 0) or 0))
        load_terms.append(int(ctx.fixed_lab_by_slot.get(slot_id, 0) or 0))

        model.Add(load == sum(load_terms))
        
        if strict_room_cap:
            model.Add(load <= int(total_available_rooms))
        else:
            # Soft capacity with true overflow penalty.
            # Penalize only the amount above total available rooms, not the full load.
            slot_capacity_overflow = model.NewIntVar(0, max_slot_load, f"slot_cap_over_{slot_id}")
            model.Add(slot_capacity_overflow >= load - int(total_available_rooms))
            model.Add(slot_capacity_overflow >= 0)
            ctx.slot_capacity_overflow_terms.append(slot_capacity_overflow)

        overload = model.NewIntVar(0, max_slot_load, f"slot_over_{slot_id}")
        model.Add(overload >= load - int(soft_threshold))
        model.Add(overload >= 0)

        ctx.slot_load_vars[slot_id] = load
        ctx.slot_overload_by_slot[slot_id] = overload
        ctx.slot_overload_terms.append(overload)
        slot_load_vars.append(load)

    if not slot_load_vars:
        return

    total_load = model.NewIntVar(0, max_slot_load * len(slot_load_vars), "total_slot_load")
    model.Add(total_load == sum(slot_load_vars))

    avg_load = model.NewIntVar(0, max_slot_load, "avg_slot_load_floor")
    n = len(slot_load_vars)
    model.Add(total_load >= avg_load * n)
    model.Add(total_load <= avg_load * n + (n - 1))

    if not strict_room_cap:
        # Softly minimize the peak slot overflow to encourage spreading classes
        # across the timetable instead of concentrating them in a few hot spots.
        peak_slot_load = model.NewIntVar(0, max_slot_load * 2, "peak_slot_load")
        model.AddMaxEquality(peak_slot_load, slot_load_vars)
        peak_slot_overflow = model.NewIntVar(0, max_slot_load, "peak_slot_overflow")
        model.Add(peak_slot_overflow >= peak_slot_load - int(total_available_rooms))
        model.Add(peak_slot_overflow >= 0)
        ctx.slot_capacity_overflow_terms.append(peak_slot_overflow)

    for ts in ctx.slots:
        slot_id = ts.id
        load = ctx.slot_load_vars.get(slot_id)
        if load is None:
            continue
        dev = model.NewIntVar(0, max_slot_load, f"slot_dev_{slot_id}")
        model.Add(dev >= load - avg_load)
        model.Add(dev >= avg_load - load)
        ctx.slot_deviation_terms.append(dev)


# ── Fixed-entry hard constraints ────────────────────────────────────────────


def _log_skip_fixed_entry(ctx: SolverContext, reason: str, **details: Any) -> None:
    """Log and skip fixed entry; do NOT make model infeasible."""
    import logging as _logging
    logger = _logging.getLogger(__name__)
    logger.warning(f"Skipped fixed entry due to: {reason}", extra=details)
    if not hasattr(ctx, 'skipped_fixed_entries'):
        ctx.skipped_fixed_entries = []
    ctx.skipped_fixed_entries.append((reason, details))


# ── Combined-group same-time enforcement ────────────────────────────────────


def _add_combined_group_selection(ctx: SolverContext) -> None:
    """HARD: Exactly one combined-group variable per group must be selected.
    
    This ensures all sections in a combined group use the SAME time slot.
    For each group_id, exactly one combined_x[(group_id, slot_id)] is = 1.
    """
    model = ctx.model
    
    for group_id, combined_vars in ctx.combined_vars_by_gid.items():
        if not combined_vars:
            continue
        
        # Exactly 1 combined variable active per group
        # This forces all sections to use the same slot
        model.Add(sum(combined_vars) == 1)
        
        gid_str = str(group_id)[:20]  # Logging label
        log.debug(f"Added combined-group same-time constraint for group {gid_str}: exactly 1 of {len(combined_vars)} vars")


# ── Lab day continuity (soft preference) ────────────────────────────────────


def _add_lab_day_continuity_preference(ctx: SolverContext) -> None:
    """SOFT: Discourage splitting a lab across non-contiguous days.
    
    For each (section, subject) pair with multiple lab sessions per week,
    prefer them to occur on nearby days (e.g., Mon-Tue) rather than 
    Mon + Wed due to cognitive load concerns.
    
    Approach: For each lab with 2+ starts on different days, create a penalty
    variable that increases when the days are far apart.
    """
    model = ctx.model
    
    # lab_starts_by_sec_subj: dict[(sec_id, subj_id)] -> list of lab_start BoolVars
    for (sec_id, subj_id), lab_start_vars in ctx.lab_starts_by_sec_subj.items():
        if len(lab_start_vars) < 2:
            continue  # Single-session labs or no labs
        
        # Group these lab starts by day
        lab_starts_by_day: dict[int, list] = defaultdict(list)
        for lab_start_var in lab_start_vars:
            # We need to look up which day this start is on
            # Search through lab_start dictionary for the matching key
            for (l_sec, l_subj, day, _slot_idx), sv in ctx.lab_start.items():
                if l_sec == sec_id and l_subj == subj_id and sv is lab_start_var:
                    lab_starts_by_day[day].append(lab_start_var)
                    break
        
        if len(lab_starts_by_day) < 2:
            continue  # All labs on one day or no split yet
        
        # days_with_labs contains days that have at least one lab start
        days_with_labs = sorted(lab_starts_by_day.keys())
        
        if len(days_with_labs) < 2:
            continue
        
        # Create penalty for day spread (e.g., if labs on day 0 and day 5, penalize)
        for d1 in days_with_labs:
            for d2 in days_with_labs:
                if d1 >= d2:
                    continue
                gap = d2 - d1
                if gap > 1:  # Non-contiguous DAYS (Mon-Tue=gap 1 is OK, Mon-Wed=gap 2 penalize)
                    penalty_var = model.NewBoolVar(f"lab_gap_penalty_{sec_id}_{subj_id}_{d1}_{d2}")
                    # penalty_var = 1 iff both days have active labs
                    vars_d1 = lab_starts_by_day.get(d1, [])
                    vars_d2 = lab_starts_by_day.get(d2, [])
                    if vars_d1 and vars_d2:
                        any_d1 = model.NewBoolVar(f"lab_any_day{d1}_")
                        any_d2 = model.NewBoolVar(f"lab_any_day{d2}_")
                        model.AddMaxEquality(any_d1, vars_d1)
                        model.AddMaxEquality(any_d2, vars_d2)
                        # penalty_var = 1 iff both any_d1 and any_d2
                        model.Add(penalty_var >= any_d1 + any_d2 - 1)
                        ctx.lab_day_gap_penalty_terms.append(penalty_var)


def _add_fixed_entry_hard_constraints(ctx: SolverContext) -> None:
    model = ctx.model
    for fe in ctx.fixed_entries:
        if str(fe.id) in ctx.locked_fixed_entry_ids:
            continue
        subj = ctx.subject_by_id.get(fe.subject_id)
        if subj is None:
            _log_skip_fixed_entry(
                ctx,
                "Fixed entry subject is not part of the current solve scope.",
                section_id=fe.section_id,
                subject_id=fe.subject_id,
                teacher_id=fe.teacher_id,
                slot_id=fe.slot_id,
            )
            continue

        di = ctx.slot_info.get(fe.slot_id)
        if di is None:
            _log_skip_fixed_entry(
                ctx,
                "Fixed entry references a time slot that does not exist.",
                section_id=fe.section_id,
                subject_id=fe.subject_id,
                teacher_id=fe.teacher_id,
                slot_id=fe.slot_id,
            )
            continue
        day, slot_idx = int(di[0]), int(di[1])

        # Combined THEORY
        gid = ctx.combined_gid_by_sec_subj.get((fe.section_id, fe.subject_id))
        if gid is not None and str(subj.subject_type) == "THEORY":
            if getattr(fe, "teacher_id", None) is not None:
                expected_tid = ctx.group_teacher_id.get(gid)
                if expected_tid is None:
                    strict_tid = None
                    for sid in ctx.group_sections.get(gid, []):
                        _tid = ctx.assigned_teacher_by_section_subject.get((sid, fe.subject_id))
                        if _tid is None:
                            strict_tid = None
                            break
                        if strict_tid is None:
                            strict_tid = _tid
                        elif strict_tid != _tid:
                            strict_tid = None
                            break
                    expected_tid = strict_tid
                if expected_tid is not None and expected_tid != fe.teacher_id:
                    _log_skip_fixed_entry(
                        ctx,
                        "Fixed combined-class teacher does not match the group's assigned teacher.",
                        section_id=fe.section_id,
                        subject_id=fe.subject_id,
                        teacher_id=fe.teacher_id,
                        slot_id=fe.slot_id,
                    )
                    continue

            gv = ctx.combined_x.get((gid, fe.slot_id))
            if gv is None:
                _log_skip_fixed_entry(
                    ctx,
                    "Fixed combined-class slot is not allowed for all sections in the group.",
                    section_id=fe.section_id,
                    subject_id=fe.subject_id,
                    teacher_id=fe.teacher_id,
                    slot_id=fe.slot_id,
                )
                continue
            model.Add(gv == 1)

            covered_slots = ctx.combined_covered_slots.get((gid, fe.slot_id), [fe.slot_id])
            for sid in ctx.group_sections.get(gid, []):
                for covered_sid in covered_slots:
                    ctx.fixed_room_by_section_slot[(sid, covered_sid)] = fe.room_id
            continue

        if str(subj.subject_type) == "LAB":
            sv = ctx.lab_start.get((fe.section_id, fe.subject_id, day, slot_idx))
            if sv is None:
                _log_skip_fixed_entry(
                    ctx,
                    "Fixed lab entry must be placed on a valid lab start slot.",
                    section_id=fe.section_id,
                    subject_id=fe.subject_id,
                    teacher_id=fe.teacher_id,
                    slot_id=fe.slot_id,
                )
                continue
            model.Add(sv == 1)

            section = ctx.section_by_id.get(fe.section_id)
            track = str(getattr(section, "track", "CORE") or "CORE")
            block = ctx.lab_block_for(fe.subject_id, track=track)
            if block < 1:
                block = 1
            for j in range(block):
                ts = ctx.slot_by_day_index.get((day, slot_idx + j))
                if ts is None:
                    continue
                ctx.fixed_room_by_section_slot[(fe.section_id, ts.id)] = fe.room_id
            continue

        # Regular THEORY start variable (duration-aware)
        key = (fe.section_id, fe.subject_id, fe.slot_id)
        xv = ctx.x.get(key)
        if xv is None:
            _log_skip_fixed_entry(
                ctx,
                "Fixed entry slot not allowed for the section or variable missing.",
                section_id=fe.section_id,
                subject_id=fe.subject_id,
                teacher_id=fe.teacher_id,
                slot_id=fe.slot_id,
            )
            continue
        model.Add(xv == 1)
        covered_slots = ctx.x_covered_slots.get(key, [fe.slot_id])
        for covered_sid in covered_slots:
            ctx.fixed_room_by_section_slot[(fe.section_id, covered_sid)] = fe.room_id


# ── Section no-overlap ──────────────────────────────────────────────────────


def _add_section_no_overlap(ctx: SolverContext) -> None:
    model = ctx.model
    for section in ctx.sections:
        for slot_id in ctx.allowed_slots_by_section[section.id]:
            terms = ctx.section_slot_terms.get((section.id, slot_id), [])
            if terms:
                model.Add(sum(terms) <= 1)


def _add_section_max_daily_slots(ctx: SolverContext) -> None:
    """Enforce sections.max_daily_slots: at most N classes per calendar day."""
    model = ctx.model
    for section in ctx.sections:
        cap = getattr(section, "max_daily_slots", None)
        if cap is None:
            continue
        cap = int(cap)
        for day in range(6):
            day_terms: list = []
            for slot_id in ctx.allowed_slots_by_section.get(section.id, set()):
                d, _ = ctx.slot_info.get(slot_id, (None, None))
                if d is not None and int(d) == day:
                    day_terms.extend(ctx.section_slot_terms.get((section.id, slot_id), []))
            if day_terms:
                model.Add(sum(day_terms) <= cap)


# ── Section compactness ─────────────────────────────────────────────────────


def _add_section_compactness(ctx: SolverContext) -> None:
    model = ctx.model
    MAX_EMPTY_GAP_SLOTS = 3

    for section in ctx.sections:
        sec_id = section.id
        for day in range(0, 6):
            day_slots = ctx.slots_by_day.get(day, [])
            if len(day_slots) < (MAX_EMPTY_GAP_SLOTS + 3):
                continue

            occ_list: list[tuple[int, cp_model.IntVar]] = []
            occ_vars: list[cp_model.IntVar] = []
            for ts in day_slots:
                terms = ctx.section_slot_terms.get((sec_id, ts.id), [])
                ov = model.NewBoolVar(f"occ_{sec_id}_{day}_{int(ts.slot_index)}")
                if terms:
                    model.Add(ov == sum(terms))
                else:
                    model.Add(ov == 0)
                occ_list.append((int(ts.slot_index), ov))
                occ_vars.append(ov)

            ctx.occ_by_section_day[(sec_id, day)] = occ_list

            # Hard max-gap constraint
            n = len(occ_vars)
            min_dist = MAX_EMPTY_GAP_SLOTS + 2
            for i in range(0, n):
                for j in range(i + min_dist, n):
                    middle = occ_vars[i + 1 : j]
                    if middle:
                        model.Add(occ_vars[i] + occ_vars[j] - sum(middle) <= 1)
                    else:
                        model.Add(occ_vars[i] + occ_vars[j] <= 1)

            # ── OPTIMIZATION: span-based soft gap penalty ──────────────────
            # Old approach created 3n-2 BoolVars per (section, day) using
            # prefix/suffix arrays plus per-slot gap BoolVars.
            #
            # New approach: 2 IntVars (first_occ, last_occ) + 1 IntVar
            # (gap_penalty = span - classes_count) per (section, day) that
            # has any classes.  This is O(1) aux vars instead of O(n).
            #
            #   gap_penalty = (last_occ_index - first_occ_index) - (sum(occ_vars) - 1)
            #               = number of empty slots inside the schedule window.
            # ───────────────────────────────────────────────────────────────
            classes_count = sum(occ_vars)  # LinearExpr

            # first_idx: minimum slot index that is occupied (N when none)
            # We model this as:  first_idx <= i * (1 − occ_vars[i]) + n*occ_vars[i]
            # But the cleanest Integer Programming approach uses AddMinEquality:
            #   represent each occ_vars[i] as "position if occupied else n"
            sentinel_first: list[cp_model.IntVar] = []
            sentinel_last: list[cp_model.IntVar] = []
            for i, ov in enumerate(occ_vars):
                # first_sentinel[i] = i if ov == 1 else n
                fv = model.NewIntVar(0, n, f"fs_{sec_id}_{day}_{i}")
                model.Add(fv == i).OnlyEnforceIf(ov)
                model.Add(fv == n).OnlyEnforceIf(ov.Not())
                sentinel_first.append(fv)
                # last_sentinel[i] = i if ov == 1 else -1
                lv = model.NewIntVar(-1, n - 1, f"ls2_{sec_id}_{day}_{i}")
                model.Add(lv == i).OnlyEnforceIf(ov)
                model.Add(lv == -1).OnlyEnforceIf(ov.Not())
                sentinel_last.append(lv)

            first_occ = model.NewIntVar(0, n, f"first_occ_{sec_id}_{day}")
            last_occ = model.NewIntVar(-1, n - 1, f"last_occ_{sec_id}_{day}")
            model.AddMinEquality(first_occ, sentinel_first)
            model.AddMaxEquality(last_occ, sentinel_last)

            # span = last_occ - first_occ  (0 when no classes: last=-1, first=n)
            # gap_penalty = span - (classes_count - 1)  when classes_count >= 1
            # We add the raw span as a soft penalty term (weighted in objective).
            # To avoid penalizing days with zero classes, we gate on any_class.
            any_class = model.NewBoolVar(f"any_class_{sec_id}_{day}")
            model.Add(classes_count >= 1).OnlyEnforceIf(any_class)
            model.Add(classes_count == 0).OnlyEnforceIf(any_class.Not())

            span = model.NewIntVar(0, n, f"span_{sec_id}_{day}")
            model.Add(span == last_occ - first_occ + 1).OnlyEnforceIf(any_class)
            model.Add(span == 0).OnlyEnforceIf(any_class.Not())

            gap_penalty = model.NewIntVar(0, n, f"gap_pen_{sec_id}_{day}")
            model.Add(gap_penalty == span - classes_count).OnlyEnforceIf(any_class)
            model.Add(gap_penalty == 0).OnlyEnforceIf(any_class.Not())

            ctx.internal_gap_terms.append(gap_penalty)
            ctx.section_gap_terms_by_section_day[(sec_id, int(day))].append(gap_penalty)


# ── Teacher constraints ─────────────────────────────────────────────────────


def _add_teacher_no_overlap(ctx: SolverContext) -> None:
    model = ctx.model
    for (_teacher_id, _slot_id), terms in ctx.teacher_slot_terms.items():
        if terms:
            model.Add(sum(terms) <= 1)


def _add_teacher_weekly_off(ctx: SolverContext) -> None:
    model = ctx.model
    for teacher_id, teacher in ctx.teacher_by_id.items():
        if teacher.weekly_off_day is None:
            continue
        off_day = int(teacher.weekly_off_day)
        if off_day not in ctx.teacher_active_days.get(teacher_id, set()):
            continue
        for ts in ctx.slots_by_day.get(off_day, []):
            terms = ctx.teacher_slot_terms.get((teacher_id, ts.id), [])
            if terms:
                model.Add(sum(terms) == 0)


def _add_teacher_workload_soft_penalties(ctx: SolverContext) -> None:
    """Convert teacher workload rules into soft penalties.

    Hard teacher no-overlap is enforced in ``_add_teacher_no_overlap``.
    This function only adds soft overload variables for:
    - weekly load above ``max_per_week``
    - daily load above ``max_per_day``
    - consecutive blocks above ``max_continuous``
    - assignments in teacher soft-window avoid slots
    """
    model = ctx.model

    for teacher_id, teacher in ctx.teacher_by_id.items():
        # Weekly overload soft variable.
        all_terms = ctx.teacher_all_terms.get(teacher_id, [])
        if all_terms:
            preferred_weekly = int(getattr(teacher, "max_per_week", 0) or 0)
            weekly_ub = 0
            for term in all_terms:
                weekly_ub += int(term) if isinstance(term, int) else 1

            weekly_load = model.NewIntVar(0, weekly_ub, f"t_weekly_load_{teacher_id}")
            model.Add(weekly_load == sum(all_terms))

            overflow = model.NewIntVar(0, weekly_ub, f"t_weekly_overflow_{teacher_id}")
            model.Add(overflow >= weekly_load - preferred_weekly)
            model.Add(overflow >= 0)

            ctx.teacher_weekly_overload_terms.append(overflow)
            ctx.teacher_weekly_overload_by_teacher[teacher_id] = overflow

        # Daily overload soft variable.
        preferred_daily = int(getattr(teacher, "max_per_day", 0) or 0)
        for day in range(0, 6):
            day_terms = ctx.teacher_day_terms.get((teacher_id, day), [])
            if not day_terms:
                continue

            day_ub = len(day_terms)
            day_load = model.NewIntVar(0, day_ub, f"t_day_load_{teacher_id}_{day}")
            model.Add(day_load == sum(day_terms))

            day_overflow = model.NewIntVar(0, day_ub, f"t_day_overflow_{teacher_id}_{day}")
            model.Add(day_overflow >= day_load - preferred_daily)
            model.Add(day_overflow >= 0)

            ctx.teacher_daily_overload_terms.append(day_overflow)
            ctx.teacher_daily_overload_by_teacher_day[(teacher_id, int(day))] = day_overflow

        # Consecutive-load overflow soft variable.
        max_cont = int(getattr(teacher, "max_continuous", 0) or 0)
        if max_cont > 0:
            for day in range(0, 6):
                if day not in ctx.teacher_active_days.get(teacher_id, set()):
                    continue
                day_slots = ctx.slots_by_day.get(day, [])
                if len(day_slots) <= max_cont:
                    continue

                window_len = max_cont + 1
                for i in range(0, len(day_slots) - window_len + 1):
                    window_slots = day_slots[i : i + window_len]
                    window_terms = []
                    for ts in window_slots:
                        window_terms.extend(ctx.teacher_slot_terms.get((teacher_id, ts.id), []))
                    if not window_terms:
                        continue

                    window_load = model.NewIntVar(0, window_len, f"t_cont_load_{teacher_id}_{day}_{i}")
                    model.Add(window_load == sum(window_terms))

                    cont_overflow = model.NewIntVar(0, window_len, f"t_cont_overflow_{teacher_id}_{day}_{i}")
                    model.Add(cont_overflow >= window_load - max_cont)
                    model.Add(cont_overflow >= 0)

                    ctx.teacher_continuity_overload_terms.append(cont_overflow)

        # Preferred slot penalty: soft-window slots are avoid slots.
        # Penalize any assignment that lands on such slots.
        for slot_id in sorted(ctx.teacher_soft_window_slots.get(teacher_id, set()), key=lambda x: str(x)):
            slot_terms = ctx.teacher_slot_terms.get((teacher_id, slot_id), [])
            if slot_terms:
                ctx.teacher_preferred_slot_penalty_terms.append(sum(slot_terms))


# ── Subject day-spread (soft) ──────────────────────────────────────────────


def _add_subject_day_spread(ctx: SolverContext) -> None:
    """Soft penalty: discourage >1 session of the same subject on the same day.

    For each (section, subject, day) where the subject already has max_per_day >= 2,
    create a penalty variable that is 1 when the section has 2+ sessions of that
    subject on the same day.  This nudges the solver to spread subjects across days
    without making it a hard constraint (which could cause infeasibility).
    """
    model = ctx.model

    # Regular theory
    for (sec_id, subj_id, day), day_x in ctx.x_by_sec_subj_day.items():
        if len(day_x) < 2:
            continue
        # If max_per_day is 1, a hard constraint already prevents doubling.
        subj = ctx.subject_by_id.get(subj_id)
        if subj is not None and ctx.max_per_day_for(subj_id) <= 1:
            continue
        # pv == 1 iff sum(day_x) >= 2
        # Linearisation:  2*pv <= total  AND  total <= 1 + pv*(N-1)
        #   pv=0 → total <= 1 (OK when total < 2)
        #   pv=1 → total >= 2 (forced)  AND  total <= N (always true)
        pv = model.NewBoolVar(f"spread_{sec_id}_{subj_id}_{day}")
        total = sum(day_x)
        model.Add(2 * pv <= total)                        # pv=1 → total >= 2
        model.Add(total <= 1 + pv * (len(day_x) - 1))    # total >= 2 → pv=1
        ctx.subject_spread_penalty_terms.append(pv)
        ctx.subject_spread_terms_by_section_day[(sec_id, int(day))].append(pv)

    # Lab sessions (day_starts with >1 start on same day)
    for (sec_id, subj_id, day), day_starts in ctx.lab_starts_by_sec_subj_day.items():
        if len(day_starts) < 2:
            continue
        subj = ctx.subject_by_id.get(subj_id)
        if subj is not None and ctx.max_per_day_for(subj_id) <= 1:
            continue
        pv = model.NewBoolVar(f"spread_lab_{sec_id}_{subj_id}_{day}")
        total = sum(day_starts)
        model.Add(2 * pv <= total)
        model.Add(total <= 1 + pv * (len(day_starts) - 1))
        ctx.subject_spread_penalty_terms.append(pv)
        ctx.subject_spread_terms_by_section_day[(sec_id, int(day))].append(pv)


# ── Teacher compactness (soft) ─────────────────────────────────────────────


def _add_teacher_compactness(ctx: SolverContext) -> None:
    """Soft penalty: minimise internal gaps in each teacher's daily schedule.

    Mirrors the section compactness logic but applied per-teacher.
    """
    model = ctx.model
    for teacher_id in ctx.teacher_by_id:
        for day in range(0, 6):
            if day not in ctx.teacher_active_days.get(teacher_id, set()):
                continue
            day_slots = ctx.slots_by_day.get(day, [])
            if len(day_slots) < 3:
                continue

            # Build per-slot occupancy for this teacher on this day
            occ_vars: list[cp_model.IntVar] = []
            for ts in day_slots:
                terms = ctx.teacher_slot_terms.get((teacher_id, ts.id), [])
                ov = model.NewBoolVar(f"tocc_{teacher_id}_{day}_{int(ts.slot_index)}")
                if terms:
                    model.AddMaxEquality(ov, terms)
                else:
                    model.Add(ov == 0)
                occ_vars.append(ov)

            n = len(occ_vars)
            if n < 3:
                continue

            # prefix[i] = 1 iff teacher has any class in slots [0..i]
            prefix: list[cp_model.IntVar] = []
            for i in range(n):
                pv = model.NewBoolVar(f"tpre_{teacher_id}_{day}_{i}")
                model.AddMaxEquality(pv, occ_vars[: i + 1])
                prefix.append(pv)

            # suffix[i] = 1 iff teacher has any class in slots [i..n-1]
            suffix: list[cp_model.IntVar] = []
            for i in range(n):
                sv = model.NewBoolVar(f"tsuf_{teacher_id}_{day}_{i}")
                model.AddMaxEquality(sv, occ_vars[i:])
                suffix.append(sv)

            # gap[i] = 1 iff slot i is empty but teacher has classes both before and after
            for i in range(1, n - 1):
                gv = model.NewBoolVar(f"tgap_{teacher_id}_{day}_{i}")
                model.Add(gv <= prefix[i - 1])
                model.Add(gv <= suffix[i + 1])
                model.Add(gv + occ_vars[i] <= 1)
                model.Add(gv >= prefix[i - 1] + suffix[i + 1] - occ_vars[i] - 1)
                ctx.teacher_gap_terms.append(gv)
                ctx.teacher_gap_terms_by_teacher_day[(teacher_id, int(day))].append(gv)


# ── Daily load balance (soft) ──────────────────────────────────────────────


def _add_daily_load_balance(ctx: SolverContext) -> None:
    """Soft penalty: discourage putting too many classes on a single day.

    For each section, compute daily load and penalise any day that exceeds
    the 'fair share' (total_sessions / active_days).
    """
    model = ctx.model

    for section in ctx.sections:
        sec_id = section.id
        # Collect all terms per day for this section
        day_term_lists: dict[int, list] = defaultdict(list)
        for day in range(0, 6):
            for slot_id in ctx.allowed_slots_by_section.get(sec_id, set()):
                info = ctx.slot_info.get(slot_id)
                if info is None or int(info[0]) != day:
                    continue
                terms = ctx.section_slot_terms.get((sec_id, slot_id), [])
                day_term_lists[day].extend(terms)

        active_days = [d for d in range(6) if day_term_lists[d]]
        if len(active_days) < 2:
            continue

        # Create a day-load var for each active day
        day_loads: list[cp_model.IntVar] = []
        for day in active_days:
            terms = day_term_lists[day]
            if not terms:
                continue
            dv = model.NewIntVar(0, len(terms), f"dload_{sec_id}_{day}")
            model.Add(dv == sum(terms))
            day_loads.append(dv)

        if len(day_loads) < 2:
            continue

        # Penalise max - min spread; use an aux variable for the max daily load
        max_load = model.NewIntVar(0, 20, f"dmax_{sec_id}")
        min_load = model.NewIntVar(0, 20, f"dmin_{sec_id}")
        model.AddMaxEquality(max_load, day_loads)
        model.AddMinEquality(min_load, day_loads)

        spread = model.NewIntVar(0, 20, f"dspread_{sec_id}")
        model.Add(spread == max_load - min_load)
        ctx.daily_load_balance_terms.append(spread)
        ctx.daily_balance_terms_by_section[sec_id].append(spread)


# ── No consecutive same-subject (hard, THEORY only) ────────────────────────


def _add_no_consecutive_same_subject(ctx: SolverContext) -> None:
    """Hard constraint: a THEORY subject cannot occupy two back-to-back slots
    for the same section on the same day.

    Labs are intentionally excluded — they use contiguous blocks by design.
    Combined-class theory vars are checked as well.
    """
    model = ctx.model

    # Regular theory vars (ctx.x keyed by (sec_id, subj_id, slot_id))
    for section in ctx.sections:
        sec_id = section.id
        for subj in ctx.subjects:
            subj_id = subj.id
            if str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
                continue
            track = str(getattr(section, "track", "CORE") or "CORE")
            if int(ctx.duration_for(subj_id, track=track) or 1) > 1:
                continue
            for day in range(6):
                day_slots = ctx.slots_by_day.get(day, [])
                for i in range(len(day_slots) - 1):
                    ts_cur = day_slots[i]
                    ts_next = day_slots[i + 1]
                    # Only enforce for truly adjacent slot indices
                    if int(ts_next.slot_index) != int(ts_cur.slot_index) + 1:
                        continue
                    xi = ctx.x.get((sec_id, subj_id, ts_cur.id))
                    xj = ctx.x.get((sec_id, subj_id, ts_next.id))
                    if xi is not None and xj is not None:
                        model.Add(xi + xj <= 1)

    # Combined-class theory vars (ctx.combined_x keyed by (gid, slot_id))
    for gid, subj_id in ctx.group_subject.items():
        subj = ctx.subject_by_id.get(subj_id)
        if subj is None or str(getattr(subj, "subject_type", "THEORY")) != "THEORY":
            continue
        group_sections = ctx.group_sections.get(gid, [])
        sample_section = ctx.section_by_id.get(group_sections[0]) if group_sections else None
        track = str(getattr(sample_section, "track", "CORE") or "CORE")
        if int(ctx.duration_for(subj_id, track=track) or 1) > 1:
            continue
        for day in range(6):
            day_slots = ctx.slots_by_day.get(day, [])
            for i in range(len(day_slots) - 1):
                ts_cur = day_slots[i]
                ts_next = day_slots[i + 1]
                if int(ts_next.slot_index) != int(ts_cur.slot_index) + 1:
                    continue
                xi = ctx.combined_x.get((gid, ts_cur.id))
                xj = ctx.combined_x.get((gid, ts_next.id))
                if xi is not None and xj is not None:
                    model.Add(xi + xj <= 1)


# ── Lunch break protection (hard) ───────────────────────────────────────────


def _add_lunch_break_constraint(ctx: SolverContext) -> None:
    """Hard constraint: no class may be scheduled during a lunch/break slot.

    Lunch slots are identified via ``ctx.lunch_slot_ids`` (populated by
    data_loader from ``time_slots.is_lunch_break = TRUE``).

    Note: ``_load_allowed_slots`` already excludes lunch slots from
    ``allowed_slots_by_section``, so theory/lab variables for those slots are
    never created.  This function enforces the constraint for combined-class
    variables and any edge case where a variable might exist for a lunch slot.
    """
    if not ctx.lunch_slot_ids:
        return

    model = ctx.model

    for slot_id in ctx.lunch_slot_ids:
        # Section-level terms (theory + lab occupancy)
        for section in ctx.sections:
            for t in ctx.section_slot_terms.get((section.id, slot_id), []):
                model.Add(t == 0)

        # Combined-class vars
        for gid in ctx.group_subject:
            gv = ctx.combined_x.get((gid, slot_id))
            if gv is not None:
                model.Add(gv == 0)
