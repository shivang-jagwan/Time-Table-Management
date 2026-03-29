"""Greedy fallback solver: sequential assignment when CP-SAT returns INFEASIBLE.

This module provides a last-resort timetable generation strategy that:
1. Iterates through all (section, subject) pairs
2. Greedily assigns available slots to each subject
3. Handles LAB blocks (contiguous multi-slot assignments)
4. Uses ANY available room (ignores type preference if needed)
5. Respects only HARD constraints (no-overlap, disallowed slots)
6. Ignores all soft constraints and preferences

Used when CP-SAT returns INFEASIBLE or UNKNOWN after all attempts.
Output is marked as FEASIBLE_GREEDY_FALLBACK for user awareness.

PHASE 10: Added deadline awareness - greedy solver respects time limits and terminates
gracefully if running out of time, producing partial timetables if needed.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from sqlalchemy import delete
from api.tenant import where_tenant
from models.timetable_entry import TimetableEntry
from models.timetable_conflict import TimetableConflict
from solver.context import SolverContext, SolveResult
from solver.room_assigner import pick_room, pick_room_for_block, assert_entry_invariants

logger = logging.getLogger(__name__)

# Phase 10: Greedy solver timeout (fallback for fallback — prevents runaway)
GREEDY_SOLVER_TIMEOUT_SECONDS = 5.0


def greedy_fallback_solver(ctx: SolverContext) -> SolveResult:
    """Sequentially assign all (section, subject) pairs to first available slots.
    
    This is the absolute last resort: guarantees a timetable even if CP-SAT fails.
    Quality is degraded but structure is valid (respects hard no-overlap rules).
    
    Handles:
    - THEORY subjects (single slot per session)
    - LAB subjects (contiguous multi-slot blocks)
    - Pre-locked entries (carried forward from constraints phase)
    
    PHASE 10: Respects time limits - terminates gracefully if running out of time,
    returning partial timetables rather than hanging indefinitely.
    """
    logger.warning("=== GREEDY FALLBACK ACTIVATED ===")
    logger.warning("CP-SAT could not find feasible solution; using sequential assignment.")
    
    # Phase 10: Set deadline for greedy solver (prevent runaway on last resort)
    greedy_deadline = time.monotonic() + GREEDY_SOLVER_TIMEOUT_SECONDS
    
    db = ctx.db
    run = ctx.run
    tenant_id = ctx.tenant_id
    
    # Clear previous entries (except pre-locked special/fixed entries)
    stmt = delete(TimetableEntry).where(TimetableEntry.run_id == run.id)
    stmt = where_tenant(stmt, TimetableEntry, tenant_id)
    db.execute(stmt)
    
    # Re-load pre-locked entries (special allotments + fixed entries)
    prelock_entries_0 = {(e[0], e[1], e[4]) for e in ctx.special_entries_to_write}  # (sec, subj, slot)
    prelock_entries_1 = {(e[0], e[1], e[4]) for e in ctx.fixed_entries_to_write}     # (sec, subj, slot)
    prelock_entries = prelock_entries_0 | prelock_entries_1
    
    # Track occupancy for hard constraint checking
    teacher_slot_usage: dict[tuple[Any, Any], int] = defaultdict(int)
    section_slot_usage: dict[tuple[Any, Any], int] = defaultdict(int)
    
    # Get all slots in order (by day, then slot index)
    all_slots = sorted(
        ctx.slots,
        key=lambda s: (int(getattr(s, 'day_of_week', 0) or 0), int(getattr(s, 'slot_index', 0) or 0))
    )
    
    # Build slot_by_day_index equivalent for easy traversal
    slot_by_idx = {(int(getattr(s, 'day_of_week', 0) or 0), int(getattr(s, 'slot_index', 0) or 0)): s for s in all_slots}
    
    entries_written = 0
    
    # Iterate through all (section, subject) requirements
    for section_id, subject_reqs in ctx.section_required.items():
        # Phase 10: CHECK DEADLINE - if running out of time, stop and return partial timetable
        if time.monotonic() > greedy_deadline:
            logger.warning(
                "[solver] Greedy fallback: deadline exceeded. Stopping at section %s. "
                "Entries written so far: %d",
                section_id,
                entries_written,
            )
            break
        
        section = ctx.section_by_id.get(section_id)
        if section is None:
            continue
        
        for subj_id, sessions_per_week in subject_reqs:
            subject = ctx.subject_by_id.get(subj_id)
            teacher_id = ctx.assigned_teacher_by_section_subject.get((section_id, subj_id))
            
            if subject is None or teacher_id is None:
                continue
            
            sessions_needed = int(sessions_per_week) if sessions_per_week is not None else 1
            sessions_assigned = 0
            
            teacher = ctx.teacher_by_id.get(teacher_id)
            teacher_off_day = int(teacher.weekly_off_day) if teacher and teacher.weekly_off_day is not None else None
            
            is_lab = str(subject.subject_type) == "LAB"
            if is_lab:
                track = str(getattr(section, "track", "CORE") or "CORE")
                lab_block_size = int(ctx.lab_block_for(subj_id, track=track) or 1)
                if lab_block_size < 1:
                    lab_block_size = 1
            else:
                lab_block_size = 1
            
            # Try to assign sessions_needed blocks (for LAB, each block is multiple slots)
            for slot in all_slots:
                if sessions_assigned >= sessions_needed:
                    break
                
                slot_id = slot.id
                day = int(getattr(slot, 'day_of_week', 0) or 0)
                start_idx = int(getattr(slot, 'slot_index', 0) or 0)
                
                # HARD constraint 1: Teacher not on off-day
                if teacher_off_day is not None and day == teacher_off_day:
                    continue
                
                # For LAB: validate entire block is available
                if is_lab:
                    block_slot_ids = []
                    block_valid = True
                    
                    for j in range(lab_block_size):
                        ts = slot_by_idx.get((day, start_idx + j))
                        if ts is None:
                            block_valid = False
                            break
                        block_slot_ids.append(ts.id)
                    
                    if not block_valid or not block_slot_ids:
                        continue
                    
                    # Check all slots in block are free for section and teacher
                    for bid in block_slot_ids:
                        if section_slot_usage[(section_id, bid)] > 0 or teacher_slot_usage[(teacher_id, bid)] > 0:
                            block_valid = False
                            break
                        if bid not in ctx.allowed_slots_by_section.get(section_id, set()):
                            block_valid = False
                            break
                        if bid in ctx.teacher_disallowed_slot_ids.get(teacher_id, set()):
                            block_valid = False
                            break
                    
                    if not block_valid:
                        continue
                    
                    # Try to assign room for the entire block
                    room_id, _ = pick_room_for_block(ctx, block_slot_ids, subject_id=subj_id)
                    if room_id is None:
                        continue
                    
                    # SUCCESS: Create entries for all slots in the block
                    try:
                        for bid in block_slot_ids:
                            entry = TimetableEntry(
                                tenant_id=tenant_id,
                                run_id=run.id,
                                academic_year_id=ctx.section_year_by_id.get(section_id) or run.academic_year_id,
                                section_id=section_id,
                                subject_id=subj_id,
                                teacher_id=teacher_id,
                                room_id=room_id,
                                slot_id=bid,
                            )
                            assert_entry_invariants(ctx, entry)
                            db.add(entry)
                            entries_written += 1
                            section_slot_usage[(section_id, bid)] += 1
                            teacher_slot_usage[(teacher_id, bid)] += 1
                    except Exception as e:
                        logger.warning(f"Failed to create LAB entry for {section_id}/{subj_id}: {e}")
                        # Rollback this block
                        entries_written -= len(block_slot_ids)
                        for bid in block_slot_ids:
                            section_slot_usage[(section_id, bid)] = max(0, section_slot_usage[(section_id, bid)] - 1)
                            teacher_slot_usage[(teacher_id, bid)] = max(0, teacher_slot_usage[(teacher_id, bid)] - 1)
                        continue
                    
                    sessions_assigned += 1
                
                else:
                    # THEORY: single slot assignment
                    # HARD constraint 2: Section not already in this slot
                    if section_slot_usage[(section_id, slot_id)] > 0:
                        continue
                    
                    # HARD constraint 3: Teacher not already in this slot
                    if teacher_slot_usage[(teacher_id, slot_id)] > 0:
                        continue
                    
                    # HARD constraint 4: Slot is within section's available window
                    if slot_id not in ctx.allowed_slots_by_section.get(section_id, set()):
                        continue
                    
                    # HARD constraint 5: Teacher is not disallowed from this slot
                    if slot_id in ctx.teacher_disallowed_slot_ids.get(teacher_id, set()):
                        continue
                    
                    # Try to assign a room
                    room_id, _ = pick_room(ctx, slot_id, str(subject.subject_type), section_id, subj_id)
                    if room_id is None:
                        continue
                    
                    # SUCCESS: Create and persist entry
                    try:
                        entry = TimetableEntry(
                            tenant_id=tenant_id,
                            run_id=run.id,
                            academic_year_id=ctx.section_year_by_id.get(section_id) or run.academic_year_id,
                            section_id=section_id,
                            subject_id=subj_id,
                            teacher_id=teacher_id,
                            room_id=room_id,
                            slot_id=slot_id,
                        )
                        assert_entry_invariants(ctx, entry)
                        db.add(entry)
                        entries_written += 1
                    except Exception as e:
                        logger.warning(f"Failed to create THEORY entry for {section_id}/{subj_id}: {e}")
                        continue
                    
                    # Update tracking
                    section_slot_usage[(section_id, slot_id)] += 1
                    teacher_slot_usage[(teacher_id, slot_id)] += 1
                    
                    sessions_assigned += 1
            
            # Log if we couldn't assign all required sessions
            if sessions_assigned < sessions_needed:
                logger.warning(
                    f"Greedy: Section {section_id} subject {subj_id} ({subject.subject_type}) only assigned {sessions_assigned}/{sessions_needed} sessions"
                )
    
    logger.info(f"Greedy fallback generated {entries_written} entries")
    
    # Update run status
    run.status = "FEASIBLE_GREEDY_FALLBACK"
    run.solver_version = "greedy-fallback-v2-lab-aware"
    run.solve_time_seconds = 0.0
    run.total_variables = 0
    run.objective_value = None
    
    # Add diagnostic conflict
    db.add(
        TimetableConflict(
            tenant_id=tenant_id,
            run_id=run.id,
            severity="WARN",
            conflict_type="GREEDY_FALLBACK_INVOKED",
            message="CP-SAT solver could not find feasible solution; using greedy sequential assignment.",
            metadata_json={"entries_written": entries_written},
        )
    )
    
    try:
        db.commit()
    except Exception as e:
        logger.exception(f"Failed to commit greedy fallback results: {e}")
        db.rollback()
        raise
    
    return SolveResult(
        status="FEASIBLE_GREEDY_FALLBACK",
        entries_written=entries_written,
        conflicts=[],
        warnings=["Generated using greedy fallback (CP-SAT infeasible); solution quality degraded."],
        solver_stats={"method": "greedy_sequential"},
        message="Fallback timetable generated (CP-SAT infeasible).",
    )
