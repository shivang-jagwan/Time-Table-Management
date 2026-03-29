"""Define the objective function for the CP-SAT model.

Multi-objective minimisation with configurable weights:
  1. Section compactness   (internal gap penalty)       — weight 500
  2. Teacher compactness   (teacher gap penalty)         — weight 300
    3. Teacher overload      (weekly + daily soft limits)  — weighted
    4. Teacher continuity    (long consecutive blocks)      — weighted
    5. Subject day-spread    (same-subject clustering)     — weight 400
    6. Daily load balance    (max-min spread per section)  — weight 300
    7. Late-slot preference  (earlier slots preferred)     — weight  10
    8. Friday last-slot      (avoid last slot on Fridays)  — weight  50
"""

from __future__ import annotations

from solver.context import SolverContext


def add_objective(ctx: SolverContext) -> None:
    """Add the minimisation objective to ``ctx.model``."""

    # ── Weights (relative importance) ────────────────────────────────────
    W_SECTION_GAP      = 500   # internal gaps hurt students the most
    W_SUBJECT_SPREAD   = 400   # spreading subjects across days aids learning
    W_TEACHER_GAP      = 300   # reduce wasted teacher wait-time
    W_DAILY_BALANCE    = 300   # even-out heavy vs light days
    W_TEACHER_OVERLOAD_WEEKLY = 700   # discourage weekly overflow but keep model feasible
    W_TEACHER_OVERLOAD_DAILY  = 520   # discourage over-packed teacher days
    W_TEACHER_CONTINUITY      = 260   # discourage long consecutive teaching streaks
    W_TEACHER_PREFERRED_SLOT  = 180   # discourage assignments in avoid/preference slots
    W_SLOT_BALANCE     = 220   # smooth class density across slots
    W_SLOT_OVERLOAD    = 500   # discourage high-density slot congestion
    W_LATE_SLOT        =  10   # 10 × slot_index: penalise later time slots
    W_FRIDAY_LAST      =  50   # flat penalty per class in the last slot on Friday
    #
    # Phase 7: Session requirement soft constraints (allow under/over-allocation)
    W_SESSION_UNDER    = 100   # Penalize fewer sessions than required (learning impact)
    W_SESSION_OVER     =  50   # Penalize more sessions than required (less impact)
    #
    # Phase 8: Room compatibility and teacher availability soft constraints
    W_ROOM_COMPATIBILITY_VIOLATION = 150  # Penalize using wrong room type/restricted rooms
    W_TEACHER_TIME_PREFERENCE_VIOLATION = 80  # Soft penalty for non-preferred time windows
    W_ELECTIVE_SYNC_VIOLATION = 120  # Soft penalty for partial elective synchronization mismatch

    # Friday is day-index 4 in the 0=Monday … 5=Saturday convention.
    FRIDAY_DAY = 4

    model = ctx.model

    # Build three priority tiers and combine with dominance scales so that
    # improving a higher-priority tier always outweighs lower-tier changes.
    tier_primary: list = []
    tier_secondary: list = []
    tier_tertiary: list = []

    # ── 1. Section internal gaps ─────────────────────────────────────────
    if ctx.internal_gap_terms:
        for gv in ctx.internal_gap_terms:
            tier_primary.append(gv * W_SECTION_GAP)

    # ── 2. Subject day-spread penalty ────────────────────────────────────
    if ctx.subject_spread_penalty_terms:
        for pv in ctx.subject_spread_penalty_terms:
            tier_primary.append(pv * W_SUBJECT_SPREAD)

    # ── 2b. Teacher weekly and daily overload penalties ────────────────
    if ctx.teacher_weekly_overload_terms:
        for ov in ctx.teacher_weekly_overload_terms:
            tier_primary.append(ov * W_TEACHER_OVERLOAD_WEEKLY)
    if ctx.teacher_daily_overload_terms:
        for ov in ctx.teacher_daily_overload_terms:
            tier_primary.append(ov * W_TEACHER_OVERLOAD_DAILY)

    # ── 2c. Slot load balancing and anti-congestion ────────────────────
    if ctx.slot_deviation_terms:
        for dv in ctx.slot_deviation_terms:
            tier_primary.append(dv * W_SLOT_BALANCE)
    if ctx.slot_overload_terms:
        for ov in ctx.slot_overload_terms:
            tier_primary.append(ov * W_SLOT_OVERLOAD)

    # ── 2d. Room capacity soft penalties (Phase 6 Stabilization) ────────
    W_THEORY_ROOM_OVERFLOW = 200   # Penalize exceeding theory room capacity
    W_LAB_ROOM_OVERFLOW    = 200   # Penalize exceeding lab room capacity
    if ctx.theory_room_overflow_terms:
        for ov in ctx.theory_room_overflow_terms:
            tier_primary.append(ov * W_THEORY_ROOM_OVERFLOW)
    if ctx.lab_room_overflow_terms:
        for ov in ctx.lab_room_overflow_terms:
            tier_primary.append(ov * W_LAB_ROOM_OVERFLOW)

    # ── 2d-PHASE11. Flexible slot capacity with soft overflow and load balancing ─
    # PHASE 11: Soft capacity allows classes to overflow beyond room count
    # but penalizes overflow to encourage class distribution across slots.
    W_SLOT_CAPACITY_OVERFLOW = 300  # Penalize exceeding total room capacity
    W_SLOT_LOAD_BALANCE_QUAD = 2    # Quadratic load balancing: discourage concentration
    
    if ctx.slot_capacity_overflow_terms:
        for overflow in ctx.slot_capacity_overflow_terms:
            tier_primary.append(overflow * W_SLOT_CAPACITY_OVERFLOW)
    
    if ctx.slot_load_squared_terms:
        for load_sq in ctx.slot_load_squared_terms:
            tier_primary.append(load_sq * W_SLOT_LOAD_BALANCE_QUAD)
    
    # ── 2e. Session requirement soft penalties (Phase 7: Convert to soft) ─
    # Penalize under-allocation (fewer sessions than required) and over-allocation
    if ctx.theory_sessions_under_terms:
        for uv in ctx.theory_sessions_under_terms:
            tier_primary.append(uv * W_SESSION_UNDER)
    if ctx.theory_sessions_over_terms:
        for ov in ctx.theory_sessions_over_terms:
            tier_primary.append(ov * W_SESSION_OVER)
    if ctx.lab_sessions_under_terms:
        for uv in ctx.lab_sessions_under_terms:
            tier_primary.append(uv * W_SESSION_UNDER)
    if ctx.lab_sessions_over_terms:
        for ov in ctx.lab_sessions_over_terms:
            tier_primary.append(ov * W_SESSION_OVER)
    if ctx.combined_sessions_under_terms:
        for uv in ctx.combined_sessions_under_terms:
            tier_primary.append(uv * W_SESSION_UNDER)
    if ctx.combined_sessions_over_terms:
        for ov in ctx.combined_sessions_over_terms:
            tier_primary.append(ov * W_SESSION_OVER)
    if ctx.elective_sessions_under_terms:
        for uv in ctx.elective_sessions_under_terms:
            tier_primary.append(uv * W_SESSION_UNDER)
    if ctx.elective_sessions_over_terms:
        for ov in ctx.elective_sessions_over_terms:
            tier_primary.append(ov * W_SESSION_OVER)

    # ── 3. Teacher internal gaps ─────────────────────────────────────────
    if ctx.teacher_gap_terms:
        for gv in ctx.teacher_gap_terms:
            tier_secondary.append(gv * W_TEACHER_GAP)

    # ── 4. Daily load balance ────────────────────────────────────────────
    if ctx.daily_load_balance_terms:
        for sv in ctx.daily_load_balance_terms:
            tier_secondary.append(sv * W_DAILY_BALANCE)

    # ── 4b. Teacher continuity and preferred-slot penalties ─────────────
    if ctx.teacher_continuity_overload_terms:
        for ov in ctx.teacher_continuity_overload_terms:
            tier_secondary.append(ov * W_TEACHER_CONTINUITY)
    if ctx.teacher_preferred_slot_penalty_terms:
        for pv in ctx.teacher_preferred_slot_penalty_terms:
            tier_secondary.append(pv * W_TEACHER_PREFERRED_SLOT)

    # ── 5. Late-slot penalty (10 × slot_index — prefer earlier slots) ─────
    # While iterating, collect any variable assigned to the last slot on
    # Friday so we can apply the Friday-last-slot penalty in section 6.
    friday_day_slots = ctx.slots_by_day.get(FRIDAY_DAY, [])
    last_friday_idx: int = (
        max(int(ts.slot_index) for ts in friday_day_slots)
        if friday_day_slots
        else -1
    )
    friday_last_terms: list = []

    for (_sec, _sid, slot_id), xv in ctx.x.items():
        d, idx = ctx.slot_info.get(slot_id, (0, 0))
        tier_tertiary.append(xv * (idx + 1) * W_LATE_SLOT)
        if d == FRIDAY_DAY and idx == last_friday_idx:
            friday_last_terms.append(xv)

    for z_key, zv in ctx.z.items():
        slot_id = None
        if isinstance(z_key, tuple):
            if len(z_key) == 2:
                _bid, slot_id = z_key
            elif len(z_key) == 3:
                _sec, _bid, slot_id = z_key
        if slot_id is None:
            continue
        d, idx = ctx.slot_info.get(slot_id, (0, 0))
        tier_tertiary.append(zv * (idx + 1) * W_LATE_SLOT)
        if d == FRIDAY_DAY and idx == last_friday_idx:
            friday_last_terms.append(zv)

    for (_sec, _sid, _day, start_idx), sv in ctx.lab_start.items():
        tier_tertiary.append(sv * (start_idx + 1) * W_LATE_SLOT)
        if _day == FRIDAY_DAY and start_idx == last_friday_idx:
            friday_last_terms.append(sv)

    # Combined theory vars — shared across sections in a combined group;
    # previously absent from the late-slot loop.
    for (_gid, slot_id), cv in ctx.combined_x.items():
        d, idx = ctx.slot_info.get(slot_id, (0, 0))
        tier_tertiary.append(cv * (idx + 1) * W_LATE_SLOT)
        if d == FRIDAY_DAY and idx == last_friday_idx:
            friday_last_terms.append(cv)

    # ── 6. Friday last-slot penalty ──────────────────────────────────────
    # Penalise each class (any variable type) scheduled in the very last
    # slot on Friday.  Adds a flat W_FRIDAY_LAST penalty per assignment.
    for term in friday_last_terms:
        tier_tertiary.append(term * W_FRIDAY_LAST)

    # Conservative upper bounds used to derive dominance scales.
    n_assign_terms = len(ctx.x) + len(ctx.z) + len(ctx.lab_start) + len(ctx.combined_x)
    max_slot_index = max((int(ts.slot_index) for ts in ctx.slots), default=0) + 1

    tertiary_bound = (
        n_assign_terms * (max_slot_index * W_LATE_SLOT + W_FRIDAY_LAST + 1)
    )
    secondary_bound = (
        len(ctx.teacher_gap_terms) * W_TEACHER_GAP
        + len(ctx.daily_load_balance_terms) * 8 * W_DAILY_BALANCE
        + len(ctx.teacher_continuity_overload_terms) * 8 * W_TEACHER_CONTINUITY
        + len(ctx.teacher_preferred_slot_penalty_terms) * W_TEACHER_PREFERRED_SLOT
        + 1
    )

    tertiary_scale = 1
    secondary_scale = max(1, tertiary_bound)
    primary_scale = max(1, tertiary_bound * secondary_bound)

    objective_terms: list = []
    if tier_primary:
        objective_terms.append(sum(tier_primary) * primary_scale)
    if tier_secondary:
        objective_terms.append(sum(tier_secondary) * secondary_scale)
    if tier_tertiary:
        objective_terms.append(sum(tier_tertiary) * tertiary_scale)

    # ── Minimise ─────────────────────────────────────────────────────────
    if objective_terms:
        model.Minimize(sum(objective_terms))
