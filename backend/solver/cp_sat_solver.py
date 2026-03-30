"""CP-SAT-based timetable solver — orchestrator.

Public API (backward-compatible):
    solve_program_year(...)  -> SolveResult
    solve_program_global(...) -> SolveResult
    SolverInvariantError
    SolveResult

The heavy lifting is split into sub-modules:
    context        — SolverContext dataclass (shared state)
    data_loader    — database queries
    pre_solve_locks— special allotments / fixed entries pre-processing
    variables      — CP-SAT BoolVar creation
    constraints    — hard & soft constraints
    objective      — objective function
    room_assigner  — greedy post-solve room assignment
    result_writer  — write TimetableEntry rows + commit
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
import time

from ortools.sat.python import cp_model
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.tenant import where_tenant
from core.db import SessionLocal
from models.section import Section
from models.timetable_entry import TimetableEntry
from models.timetable_conflict import TimetableConflict
from models.timetable_run import TimetableRun

# Re-export for backward compatibility
from solver.context import SolveResult, SolverContext, SolverInvariantError  # noqa: F401

import logging

from solver.constraints import add_constraints
from solver.data_loader import load_all, build_pruned_slots, _validate_domain_reduction
from solver.hybrid_loop import run_hybrid_repair_loop
from solver.hybrid_initializer import generate_hybrid_hints
from solver.initialization_engine import build_initialization_modes, generate_initial_hints
from solver.lns_strategies import build_lns_hints, choose_lns_strategy
from solver.objective import add_objective
from solver.pre_solve_locks import apply_pre_solve_locks, check_teacher_window_feasibility, validate_pre_solve_locks
from solver.result_writer import write_results
from solver.variables import create_variables

logger = logging.getLogger(__name__)


# Hard solver governance limits.
HARD_SINGLE_SOLVE_LIMIT_SECONDS = 30.0
HARD_TOTAL_SOLVE_LIMIT_SECONDS = 60.0
MAX_RESTARTS = 3
MAX_ITERATIONS = 5
DEFAULT_NUM_SEARCH_WORKERS = 8
DEFAULT_RANDOM_SEED = 42
DEFAULT_MAX_CONFLICTS = 100_000
MIN_BUDGET_SLICE_SECONDS = 1.0


def _cap_total_budget_seconds(max_time_seconds: float) -> float:
    return max(MIN_BUDGET_SLICE_SECONDS, min(float(max_time_seconds), HARD_TOTAL_SOLVE_LIMIT_SECONDS))


def _remaining_seconds(deadline_monotonic: float | None) -> float | None:
    if deadline_monotonic is None:
        return None
    return max(0.0, float(deadline_monotonic) - time.monotonic())


def _cap_single_solve_budget_seconds(
    requested_seconds: float,
    *,
    deadline_monotonic: float | None = None,
) -> float:
    budget = max(0.0, min(float(requested_seconds), HARD_SINGLE_SOLVE_LIMIT_SECONDS))
    remaining = _remaining_seconds(deadline_monotonic)
    if remaining is not None:
        budget = min(budget, remaining)
    return max(0.0, budget)


def _is_deadline_exceeded(deadline_monotonic: float | None) -> bool:
    remaining = _remaining_seconds(deadline_monotonic)
    return remaining is not None and remaining <= 0.0


def _estimate_adaptive_budget_seconds(
    *,
    requested_cap: float,
    num_vars: int,
    num_constraints: int,
    sections: int,
    teachers: int,
    slots: int,
    require_optimal: bool,
) -> float:
    """Estimate a model-size-aware solve budget bounded by requested cap.

    This improves throughput on small instances while preserving time for
    larger/harder instances.
    """
    complexity = (
        float(num_vars)
        + 0.65 * float(num_constraints)
        + 40.0 * float(sections)
        + 20.0 * float(teachers)
        + 5.0 * float(slots)
    )
    adaptive = 5.0 + (complexity / 350.0)
    if require_optimal:
        adaptive *= 1.15
    adaptive = max(MIN_BUDGET_SLICE_SECONDS, min(float(requested_cap), adaptive))
    return adaptive


def solve_program_year(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    academic_year_id,
    seed: int | None,
    max_time_seconds: float,
    enforce_teacher_load_limits: bool = True,
    require_optimal: bool = False,
    allow_extended_solve: bool = False,
    hybrid_init_enabled: bool = False,
    hybrid_population_size: int = 24,
    hybrid_generations: int = 20,
    multi_seed_restarts: int = 1,
    lns_iterations: int = 0,
    lns_keep_fraction: float = 0.7,
) -> SolveResult:
    total_budget = _cap_total_budget_seconds(max_time_seconds)
    deadline_monotonic = time.monotonic() + total_budget
    bounded_restarts = min(MAX_RESTARTS, max(1, int(multi_seed_restarts or 1)))
    bounded_lns_iterations = min(MAX_ITERATIONS, max(0, int(lns_iterations or 0)))

    if bounded_restarts <= 1 and bounded_lns_iterations <= 0:
        return _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=seed,
            max_time_seconds=total_budget,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            solve_deadline_monotonic=deadline_monotonic,
        )

    return _solve_program_with_restarts(
        db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        base_seed=seed,
        max_time_seconds=total_budget,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        allow_extended_solve=allow_extended_solve,
        hybrid_init_enabled=hybrid_init_enabled,
        hybrid_population_size=hybrid_population_size,
        hybrid_generations=hybrid_generations,
        num_restarts=bounded_restarts,
        lns_iterations=bounded_lns_iterations,
        lns_keep_fraction=lns_keep_fraction,
        solve_deadline_monotonic=deadline_monotonic,
    )


def solve_program_global(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    seed: int | None,
    max_time_seconds: float,
    enforce_teacher_load_limits: bool = True,
    require_optimal: bool = False,
    allow_extended_solve: bool = False,
    hybrid_init_enabled: bool = False,
    hybrid_population_size: int = 24,
    hybrid_generations: int = 20,
    multi_seed_restarts: int = 1,
    lns_iterations: int = 0,
    lns_keep_fraction: float = 0.7,
) -> SolveResult:
    """Program-wide solve across all academic years via decomposed batches.

    Phase-1 scalable architecture: partition by academic year, solve incrementally,
    and carry teacher slot usage globally across partitions.
    """
    total_budget = _cap_total_budget_seconds(max_time_seconds)
    deadline_monotonic = time.monotonic() + total_budget
    bounded_restarts = min(MAX_RESTARTS, max(1, int(multi_seed_restarts or 1)))
    bounded_lns_iterations = min(MAX_ITERATIONS, max(0, int(lns_iterations or 0)))

    return _solve_program_global_decomposed(
        db,
        run=run,
        program_id=program_id,
        seed=seed,
        max_time_seconds=total_budget,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        allow_extended_solve=allow_extended_solve,
        hybrid_init_enabled=hybrid_init_enabled,
        hybrid_population_size=hybrid_population_size,
        hybrid_generations=hybrid_generations,
        multi_seed_restarts=bounded_restarts,
        lns_iterations=bounded_lns_iterations,
        lns_keep_fraction=lns_keep_fraction,
        solve_deadline_monotonic=deadline_monotonic,
    )


def _collect_teacher_schedule_map_for_run(
    db: Session,
    *,
    run_id,
    tenant_id,
) -> dict[Any, set[Any]]:
    schedule: dict[Any, set[Any]] = defaultdict(set)
    q = select(TimetableEntry.teacher_id, TimetableEntry.slot_id).where(TimetableEntry.run_id == run_id)
    q = where_tenant(q, TimetableEntry, tenant_id)
    for teacher_id, slot_id in db.execute(q).all():
        schedule[teacher_id].add(slot_id)
    return schedule


def _collect_conflict_ids_for_run(
    db: Session,
    *,
    run_id,
    tenant_id,
) -> set[Any]:
    ids: set[Any] = set()
    q = select(TimetableConflict.id).where(TimetableConflict.run_id == run_id)
    q = where_tenant(q, TimetableConflict, tenant_id)
    for (conflict_id,) in db.execute(q).all():
        ids.add(conflict_id)
    return ids


def _clear_run_state_for_sections(
    db: Session,
    *,
    run_id,
    tenant_id,
    section_ids: set[Any],
    keep_conflict_ids: set[Any],
) -> None:
    if section_ids:
        entry_stmt = (
            delete(TimetableEntry)
            .where(TimetableEntry.run_id == run_id)
            .where(TimetableEntry.section_id.in_(list(section_ids)))
        )
        entry_stmt = where_tenant(entry_stmt, TimetableEntry, tenant_id)
        db.execute(entry_stmt)

    current_conflict_ids = _collect_conflict_ids_for_run(
        db,
        run_id=run_id,
        tenant_id=tenant_id,
    )
    stale_conflict_ids = [cid for cid in current_conflict_ids if cid not in keep_conflict_ids]
    if stale_conflict_ids:
        conflict_stmt = (
            delete(TimetableConflict)
            .where(TimetableConflict.run_id == run_id)
            .where(TimetableConflict.id.in_(stale_conflict_ids))
        )
        conflict_stmt = where_tenant(conflict_stmt, TimetableConflict, tenant_id)
        db.execute(conflict_stmt)


def _chunk_section_ids(section_ids: list[Any], *, chunk_size: int) -> list[list[Any]]:
    if not section_ids:
        return []
    size = max(1, int(chunk_size))
    return [section_ids[i : i + size] for i in range(0, len(section_ids), size)]


def _solve_program_global_decomposed(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    seed: int | None,
    max_time_seconds: float,
    enforce_teacher_load_limits: bool,
    require_optimal: bool,
    allow_extended_solve: bool,
    hybrid_init_enabled: bool,
    hybrid_population_size: int,
    hybrid_generations: int,
    multi_seed_restarts: int,
    lns_iterations: int,
    lns_keep_fraction: float,
    solve_deadline_monotonic: float | None = None,
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)
    orchestration_started = time.monotonic()
    termination_reason = "COMPLETED"
    batches_executed = 0
    failed_batch_index: int | None = None
    failed_batch_year_id: Any | None = None
    failed_batch_sections: int | None = None
    backtrack_retry_attempted = False
    backtrack_retry_recovered = False

    batch_remaining_budget_before: list[float] = []
    batch_warnings_len_before: list[int] = []
    batch_combined_conflicts_len_before: list[int] = []
    batch_entries_written_before: list[int] = []
    batch_executed_before: list[int] = []
    batch_conflict_ids_before: list[set[Any]] = []

    q_years = (
        select(Section.id, Section.academic_year_id)
        .where(Section.program_id == program_id)
        .where(Section.is_active.is_(True))
    )
    q_years = where_tenant(q_years, Section, tenant_id)
    year_section_counts: dict[Any, int] = defaultdict(int)
    year_section_ids: dict[Any, list[Any]] = defaultdict(list)
    for section_id, year_id in db.execute(q_years).all():
        if year_id is None:
            continue
        year_section_counts[year_id] += 1
        year_section_ids[year_id].append(section_id)
    year_ids = sorted(year_section_counts.keys())

    # Fallback to single-model solve if no year-scoped sections were found.
    if not year_ids:
        return _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=None,
            seed=seed,
            max_time_seconds=_cap_single_solve_budget_seconds(
                max_time_seconds,
                deadline_monotonic=solve_deadline_monotonic,
            ),
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            solve_deadline_monotonic=solve_deadline_monotonic,
        )

    teacher_schedule_map: dict[Any, set[Any]] = defaultdict(set)
    combined_conflicts: list[TimetableConflict] = []
    total_entries_written = 0
    total_warnings: list[str] = []
    remaining_budget = float(max_time_seconds)
    last_result: SolveResult | None = None

    batch_units: list[tuple[Any, list[Any]]] = []
    for year_id in year_ids:
        sec_ids = sorted(year_section_ids.get(year_id, []), key=lambda x: str(x))
        # Dynamic split for heavy batches: break year-level solves by sections.
        if len(sec_ids) > 12:
            for sub in _chunk_section_ids(sec_ids, chunk_size=8):
                batch_units.append((year_id, sub))
        else:
            batch_units.append((year_id, sec_ids))

    for idx, (year_id, section_subset) in enumerate(batch_units):
        remaining_wall = _remaining_seconds(solve_deadline_monotonic)
        if remaining_wall is not None and remaining_wall <= 0.0:
            termination_reason = "GLOBAL_TIME_LIMIT_REACHED"
            logger.warning(
                "[solver] global decomposed deadline reached before batch %d/%d",
                idx + 1,
                len(batch_units),
            )
            break

        remaining_units = batch_units[idx:]
        remaining_weight = float(sum(max(1, len(sec_ids)) for _yid, sec_ids in remaining_units))
        this_weight = float(max(1, len(section_subset)))
        proportional_budget = remaining_budget * (this_weight / max(1.0, remaining_weight))
        batch_budget = _cap_single_solve_budget_seconds(
            proportional_budget,
            deadline_monotonic=solve_deadline_monotonic,
        )
        if batch_budget < MIN_BUDGET_SLICE_SECONDS:
            termination_reason = "INSUFFICIENT_BUDGET_FOR_NEXT_BATCH"
            logger.warning(
                "[solver] global decomposed stopping before batch %d/%d due to low budget (%.2fs)",
                idx + 1,
                len(batch_units),
                batch_budget,
            )
            break

        logger.info(
            "[solver] global decomposed batch=%d/%d year_id=%s budget=%.1fs sections_in_batch=%d blocked_teachers=%d",
            idx + 1,
            len(batch_units),
            str(year_id),
            batch_budget,
            len(section_subset),
            len(teacher_schedule_map),
        )

        batch_remaining_budget_before.append(float(remaining_budget))
        batch_warnings_len_before.append(len(total_warnings))
        batch_combined_conflicts_len_before.append(len(combined_conflicts))
        batch_entries_written_before.append(int(total_entries_written))
        batch_executed_before.append(int(batches_executed))
        batch_conflict_ids_before.append(
            _collect_conflict_ids_for_run(
                db,
                run_id=run.id,
                tenant_id=tenant_id,
            )
        )

        result = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=year_id,
            section_id_subset=set(section_subset),
            seed=seed,
            max_time_seconds=batch_budget,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            clear_existing_entries=(idx == 0),
            external_teacher_blocked_slot_ids=teacher_schedule_map,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            hints=None,
            initialization_mode="heuristic",
            persist_results=True,
            suppress_terminal_status_update=(idx < (len(batch_units) - 1)),
            solve_deadline_monotonic=solve_deadline_monotonic,
        )
        batches_executed += 1
        last_result = result
        combined_conflicts.extend(result.conflicts)
        total_warnings.extend(result.warnings)
        total_entries_written += int(result.entries_written)

        # Refresh global teacher usage from what has been persisted so far.
        teacher_schedule_map = _collect_teacher_schedule_map_for_run(
            db,
            run_id=run.id,
            tenant_id=tenant_id,
        )

        elapsed = float(result.solve_time_seconds or 0.0)
        remaining_budget = max(0.0, remaining_budget - elapsed)

        status_upper = str(result.status).upper()
        if status_upper in {"INFEASIBLE", "ERROR", "VALIDATION_FAILED"}:
            can_backtrack_retry = (
                status_upper == "INFEASIBLE"
                and idx > 0
                and not backtrack_retry_attempted
            )
            if can_backtrack_retry:
                backtrack_retry_attempted = True
                prev_idx = idx - 1
                prev_year_id, prev_section_subset = batch_units[prev_idx]
                replay_section_ids = set(prev_section_subset) | set(section_subset)
                replay_seed_base = (int(seed) if seed is not None else int(DEFAULT_RANDOM_SEED)) + 101 + int(prev_idx)

                logger.warning(
                    "[solver] backtrack retry start: replay batches %d and %d seed_base=%d",
                    prev_idx + 1,
                    idx + 1,
                    replay_seed_base,
                )

                try:
                    _clear_run_state_for_sections(
                        db,
                        run_id=run.id,
                        tenant_id=tenant_id,
                        section_ids=replay_section_ids,
                        keep_conflict_ids=set(batch_conflict_ids_before[prev_idx]),
                    )
                    db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    termination_reason = "BACKTRACK_RETRY_STATE_RESET_FAILED"
                    failed_batch_index = int(idx + 1)
                    failed_batch_year_id = year_id
                    failed_batch_sections = int(len(section_subset))
                    logger.exception("[solver] backtrack retry failed while resetting run state")
                    break

                teacher_schedule_map = _collect_teacher_schedule_map_for_run(
                    db,
                    run_id=run.id,
                    tenant_id=tenant_id,
                )
                remaining_budget = float(batch_remaining_budget_before[prev_idx])
                total_warnings = total_warnings[: batch_warnings_len_before[prev_idx]]
                combined_conflicts = combined_conflicts[: batch_combined_conflicts_len_before[prev_idx]]
                total_entries_written = int(batch_entries_written_before[prev_idx])
                batches_executed = int(batch_executed_before[prev_idx])

                replay_failed = False
                replay_plan = [
                    (prev_idx, prev_year_id, prev_section_subset, replay_seed_base),
                    (idx, year_id, section_subset, replay_seed_base + 1),
                ]

                for replay_idx, replay_year_id, replay_sections, replay_seed in replay_plan:
                    replay_remaining_wall = _remaining_seconds(solve_deadline_monotonic)
                    if replay_remaining_wall is not None and replay_remaining_wall <= 0.0:
                        termination_reason = "GLOBAL_TIME_LIMIT_REACHED_DURING_BACKTRACK"
                        replay_failed = True
                        failed_batch_index = int(replay_idx + 1)
                        failed_batch_year_id = replay_year_id
                        failed_batch_sections = int(len(replay_sections))
                        break

                    replay_remaining_units = batch_units[replay_idx:]
                    replay_remaining_weight = float(
                        sum(max(1, len(sec_ids)) for _yid, sec_ids in replay_remaining_units)
                    )
                    replay_weight = float(max(1, len(replay_sections)))
                    replay_proportional_budget = remaining_budget * (replay_weight / max(1.0, replay_remaining_weight))
                    replay_budget = _cap_single_solve_budget_seconds(
                        replay_proportional_budget,
                        deadline_monotonic=solve_deadline_monotonic,
                    )
                    if replay_budget < MIN_BUDGET_SLICE_SECONDS:
                        termination_reason = "INSUFFICIENT_BUDGET_FOR_BACKTRACK_REPLAY"
                        replay_failed = True
                        failed_batch_index = int(replay_idx + 1)
                        failed_batch_year_id = replay_year_id
                        failed_batch_sections = int(len(replay_sections))
                        break

                    logger.info(
                        "[solver] backtrack replay batch=%d/%d year_id=%s budget=%.1fs seed=%d",
                        replay_idx + 1,
                        len(batch_units),
                        str(replay_year_id),
                        replay_budget,
                        int(replay_seed),
                    )

                    replay_result = _solve_program(
                        db,
                        run=run,
                        program_id=program_id,
                        academic_year_id=replay_year_id,
                        section_id_subset=set(replay_sections),
                        seed=int(replay_seed),
                        max_time_seconds=replay_budget,
                        enforce_teacher_load_limits=enforce_teacher_load_limits,
                        require_optimal=require_optimal,
                        allow_extended_solve=allow_extended_solve,
                        clear_existing_entries=False,
                        external_teacher_blocked_slot_ids=teacher_schedule_map,
                        hybrid_init_enabled=hybrid_init_enabled,
                        hybrid_population_size=hybrid_population_size,
                        hybrid_generations=hybrid_generations,
                        hints=None,
                        initialization_mode="heuristic",
                        persist_results=True,
                        suppress_terminal_status_update=(replay_idx < (len(batch_units) - 1)),
                        solve_deadline_monotonic=solve_deadline_monotonic,
                    )
                    batches_executed += 1
                    last_result = replay_result
                    combined_conflicts.extend(replay_result.conflicts)
                    total_warnings.extend(replay_result.warnings)
                    total_entries_written += int(replay_result.entries_written)

                    teacher_schedule_map = _collect_teacher_schedule_map_for_run(
                        db,
                        run_id=run.id,
                        tenant_id=tenant_id,
                    )
                    replay_elapsed = float(replay_result.solve_time_seconds or 0.0)
                    remaining_budget = max(0.0, remaining_budget - replay_elapsed)

                    replay_status = str(replay_result.status).upper()
                    if replay_status in {"INFEASIBLE", "ERROR", "VALIDATION_FAILED"}:
                        termination_reason = f"TERMINAL_STATUS_{replay_status}_AFTER_BACKTRACK"
                        replay_failed = True
                        failed_batch_index = int(replay_idx + 1)
                        failed_batch_year_id = replay_year_id
                        failed_batch_sections = int(len(replay_sections))
                        break

                    if replay_idx < (len(batch_units) - 1):
                        try:
                            run.status = "CREATED"
                            run.notes = f"GLOBAL_DECOMPOSED_PROGRESS {replay_idx + 1}/{len(batch_units)}"
                            db.commit()
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass

                if not replay_failed:
                    backtrack_retry_recovered = True
                    failed_batch_index = None
                    failed_batch_year_id = None
                    failed_batch_sections = None
                    total_warnings.append(
                        "Recovered from a decomposed-batch infeasibility via one-step backtrack retry."
                    )
                    logger.info(
                        "[solver] backtrack retry recovered: batches %d and %d replayed successfully",
                        prev_idx + 1,
                        idx + 1,
                    )
                    continue

                break

            termination_reason = f"TERMINAL_STATUS_{status_upper}"
            failed_batch_index = int(idx + 1)
            failed_batch_year_id = year_id
            failed_batch_sections = int(len(section_subset))
            break

        # Intermediate decomposed batches must not expose terminal statuses.
        # Keep polling semantics stable: RUNNING until the final batch finishes.
        if idx < (len(batch_units) - 1):
            try:
                run.status = "CREATED"
                run.notes = f"GLOBAL_DECOMPOSED_PROGRESS {idx + 1}/{len(batch_units)}"
                db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

    if last_result is None:
        return SolveResult(
            status="ERROR",
            entries_written=0,
            conflicts=[],
            message="Solver stopped before processing any global batch due to time-limit guard.",
        )

    total_elapsed = max(0.0, time.monotonic() - orchestration_started)
    final_status = str(last_result.status)
    final_message = last_result.message

    if termination_reason not in {"COMPLETED", f"TERMINAL_STATUS_{final_status}"}:
        if final_status in {"OPTIMAL", "FEASIBLE"}:
            final_status = "SUBOPTIMAL"
        elif final_status not in {"INFEASIBLE", "ERROR", "VALIDATION_FAILED", "SUBOPTIMAL"}:
            final_status = "ERROR"
        total_warnings.append(
            f"Global solve terminated early: {termination_reason}."
        )
        final_message = (
            "Global solve terminated early by strict time-limit guard. "
            "Partial persisted results may be available."
        )

    if termination_reason.startswith("TERMINAL_STATUS_INFEASIBLE") and batches_executed < len(batch_units):
        # Avoid misleading "needs more time" messaging when the final stop was a hard infeasibility.
        total_warnings = [
            w for w in total_warnings
            if "optimality was not proven" not in str(w).lower()
        ]
        total_warnings.append(
            "Partial timetable entries were created for earlier batches, but a later batch is infeasible "
            "under current hard constraints (not just a time-limit issue)."
        )
        if not final_message:
            final_message = (
                "Global solve created partial results, then hit an infeasible batch. "
                "Review INFEASIBLE conflict diagnostics for the failing batch."
            )

    merged_solver_stats = dict(last_result.solver_stats or {})
    merged_solver_stats["global_telemetry"] = {
        "termination_reason": str(termination_reason),
        "batches_total": int(len(batch_units)),
        "batches_executed": int(batches_executed),
        "wall_time_seconds": float(round(total_elapsed, 3)),
        "hard_total_time_limit_seconds": float(HARD_TOTAL_SOLVE_LIMIT_SECONDS),
        "backtrack_retry_attempted": bool(backtrack_retry_attempted),
        "backtrack_retry_recovered": bool(backtrack_retry_recovered),
        **({"failed_batch_index": int(failed_batch_index)} if failed_batch_index is not None else {}),
        **({"failed_batch_year_id": str(failed_batch_year_id)} if failed_batch_year_id is not None else {}),
        **({"failed_batch_sections": int(failed_batch_sections)} if failed_batch_sections is not None else {}),
    }

    try:
        run.status = str(final_status)
        run.notes = (
            f"GLOBAL_DECOMPOSED {termination_reason} "
            f"{int(batches_executed)}/{int(len(batch_units))} "
            f"elapsed={total_elapsed:.1f}s"
        )[:500]
        db.add(run)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    return SolveResult(
        status=str(final_status),
        entries_written=total_entries_written,
        conflicts=combined_conflicts,
        diagnostics=list(last_result.diagnostics or []),
        reason_summary=last_result.reason_summary,
        objective_score=last_result.objective_score,
        warnings=total_warnings,
        solver_stats=merged_solver_stats,
        best_objective_bound=last_result.best_objective_bound,
        optimality_gap=last_result.optimality_gap,
        solve_time_seconds=total_elapsed,
        message=final_message,
    )


def _check_subject_allowed_rooms(ctx: SolverContext) -> list[str]:
    """Return warnings where subject allowed-rooms are misconfigured."""
    warnings: list[str] = []
    for subj_id, room_ids in ctx.allowed_rooms_by_subject.items():
        subj = ctx.subject_by_id.get(subj_id)
        if subj is None:
            continue
        subj_type = str(subj.subject_type).upper()
        expected_type = "LAB" if subj_type == "LAB" else None  # THEORY allows any non-special room

        valid_count = 0
        for rid in room_ids:
            room = ctx.room_by_id.get(rid)
            if room is None:
                continue
            rt = str(room.room_type).upper()
            if expected_type is None or rt == expected_type:
                valid_count += 1

        if valid_count == 0 and room_ids:
            warnings.append(
                f"Subject '{getattr(subj, 'code', subj_id)}' has {len(room_ids)} allowed room(s) "
                f"but none match subject type '{subj_type}'. Solver will fall back to default pool."
            )
    return warnings


def _is_feasible_status(status: str) -> bool:
    return str(status).upper() in {"OPTIMAL", "FEASIBLE"}


def _is_better_solution(new: SolveResult, best: SolveResult | None) -> bool:
    if not _is_feasible_status(new.status):
        return False
    if best is None:
        return True
    if not _is_feasible_status(best.status):
        return True
    if new.objective_score is None:
        return False
    if best.objective_score is None:
        return True
    return new.objective_score < best.objective_score


def _extract_solution_hints(ctx: SolverContext, solver: cp_model.CpSolver) -> dict[str, set[Any]]:
    hints = {
        "x": set(),
        "z": set(),
        "lab_start": set(),
        "combined_x": set(),
    }
    for key, var in ctx.x.items():
        try:
            if solver.Value(var) == 1:
                hints["x"].add(key)
        except Exception:
            pass
    for key, var in ctx.z.items():
        try:
            if solver.Value(var) == 1:
                hints["z"].add(key)
        except Exception:
            pass
    for key, var in ctx.lab_start.items():
        try:
            if solver.Value(var) == 1:
                hints["lab_start"].add(key)
        except Exception:
            pass
    for key, var in ctx.combined_x.items():
        try:
            if solver.Value(var) == 1:
                hints["combined_x"].add(key)
        except Exception:
            pass
    return hints


def _build_lns_feedback(
    ctx: SolverContext,
    solution_hints: dict[str, set[Any]],
    solver: cp_model.CpSolver,
    deadline_monotonic: float | None = None,
) -> dict[str, Any]:
    """Build LNS feedback from current solution (Phase 8: non-blocking diagnostics).
    
    PHASE 8 ENHANCEMENT: Added deadline-aware early exit. If near deadline,
    return minimal feedback to avoid blocking solver completion.
    All operations wrapped in try/except to ensure diagnostics never crash solve.
    """
    # Phase 8: Early exit if deadline exceeded
    if deadline_monotonic is not None:
        remaining = max(0.0, deadline_monotonic - time.monotonic())
        if remaining <= MIN_BUDGET_SLICE_SECONDS:
            logger.debug("[solver] _build_lns_feedback: deadline exceeded, returning minimal feedback")
            return {"teacher_hotspots": [], "section_hotspots": []}
    
    # Phase 8: Wrap entire function in try/except to prevent crash
    try:
        return _build_lns_feedback_impl(ctx, solution_hints, solver)
    except Exception as e:
        logger.warning(
            "[solver] _build_lns_feedback failed (Phase 8 non-blocking diagnostics): %s. "
            "Returning minimal feedback to avoid blocking solver.",
            str(e),
        )
        return {"teacher_hotspots": [], "section_hotspots": []}


def _build_lns_feedback_impl(
    ctx: SolverContext,
    solution_hints: dict[str, set[Any]],
    solver: cp_model.CpSolver,
) -> dict[str, Any]:
    """Implementation of LNS feedback calculation (Phase 8: extracted for cleaner error handling)."""
    teacher_load: dict[Any, int] = defaultdict(int)
    section_load: dict[Any, int] = defaultdict(int)
    x_keys_by_teacher: dict[Any, list[Any]] = defaultdict(list)
    x_keys_by_section: dict[Any, list[Any]] = defaultdict(list)
    x_keys_by_slot: dict[Any, list[Any]] = defaultdict(list)
    high_penalty_x_keys: list[Any] = []

    for key in solution_hints.get("x", set()):
        sec_id, subj_id, slot_id = key
        teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
        if teacher_id is not None:
            teacher_load[teacher_id] += 1
            x_keys_by_teacher[teacher_id].append(key)
        section_load[sec_id] += 1
        x_keys_by_section[sec_id].append(key)
        x_keys_by_slot[slot_id].append(key)

        _day, slot_idx = ctx.slot_info.get(slot_id, (0, 0))
        if int(slot_idx) >= 5:
            high_penalty_x_keys.append(key)

    # True objective attribution scores by owner.
    # Keep weights in sync with objective.py.
    W_SECTION_GAP = 500
    W_SUBJECT_SPREAD = 400
    W_TEACHER_GAP = 300
    W_DAILY_BALANCE = 300

    section_penalty_score: dict[Any, int] = defaultdict(int)
    teacher_penalty_score: dict[Any, int] = defaultdict(int)

    for (sec_id, _day), terms in ctx.section_gap_terms_by_section_day.items():
        for term in terms:
            try:
                section_penalty_score[sec_id] += int(solver.Value(term)) * W_SECTION_GAP
            except Exception:
                pass

    for (sec_id, _day), terms in ctx.subject_spread_terms_by_section_day.items():
        for term in terms:
            try:
                section_penalty_score[sec_id] += int(solver.Value(term)) * W_SUBJECT_SPREAD
            except Exception:
                pass

    for sec_id, terms in ctx.daily_balance_terms_by_section.items():
        for term in terms:
            try:
                section_penalty_score[sec_id] += int(solver.Value(term)) * W_DAILY_BALANCE
            except Exception:
                pass

    for (teacher_id, _day), terms in ctx.teacher_gap_terms_by_teacher_day.items():
        for term in terms:
            try:
                teacher_penalty_score[teacher_id] += int(solver.Value(term)) * W_TEACHER_GAP
            except Exception:
                pass

    teacher_hotspots = [
        tid
        for tid, _score in sorted(
            teacher_penalty_score.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    section_hotspots = [
        sid
        for sid, _score in sorted(
            section_penalty_score.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]

    # Fall back to load-based hotspots if objective-attribution scores are empty.
    if not teacher_hotspots:
        teacher_hotspots = [
            tid for tid, _cnt in sorted(teacher_load.items(), key=lambda item: item[1], reverse=True)
        ]
    if not section_hotspots:
        section_hotspots = [
            sid for sid, _cnt in sorted(section_load.items(), key=lambda item: item[1], reverse=True)
        ]

    congested_slots: list[Any] = []
    slot_load_by_slot: dict[Any, int] = {}
    overload_by_slot: dict[Any, int] = {}
    slot_day_by_slot: dict[Any, int] = {}
    try:
        for slot_id, v in ctx.slot_load_vars.items():
            slot_load_by_slot[slot_id] = int(solver.Value(v))
            slot_day_by_slot[slot_id] = int((ctx.slot_info.get(slot_id) or (0, 0))[0])
        for slot_id, v in ctx.slot_overload_by_slot.items():
            overload_by_slot[slot_id] = int(solver.Value(v))

        ranked = sorted(
            ctx.slot_load_vars.keys(),
            key=lambda sid: (
                int(overload_by_slot.get(sid, 0)),
                int(slot_load_by_slot.get(sid, 0)),
            ),
            reverse=True,
        )
        congested_slots = [
            sid
            for sid in ranked
            if int(overload_by_slot.get(sid, 0)) > 0 or int(slot_load_by_slot.get(sid, 0)) > 0
        ][:12]
    except Exception:
        congested_slots = []

    return {
        "teacher_hotspots": teacher_hotspots,
        "section_hotspots": section_hotspots,
        "teacher_penalty_score": dict(teacher_penalty_score),
        "section_penalty_score": dict(section_penalty_score),
        "x_keys_by_teacher": {k: list(v) for k, v in x_keys_by_teacher.items()},
        "x_keys_by_section": {k: list(v) for k, v in x_keys_by_section.items()},
        "x_keys_by_slot": {k: list(v) for k, v in x_keys_by_slot.items()},
        "congested_slots": list(congested_slots),
        "slot_load_by_slot": dict(slot_load_by_slot),
        "slot_overload_by_slot": dict(overload_by_slot),
        "slot_day_by_slot": dict(slot_day_by_slot),
        "high_penalty_x_keys": high_penalty_x_keys,
    }


def _score_for_pool(result: SolveResult) -> tuple[int, int]:
    if not _is_feasible_status(result.status):
        return (1, 10**18)
    objective = int(result.objective_score) if result.objective_score is not None else 10**17
    return (0, objective)


def _clone_hints(hints: dict[str, set[Any]]) -> dict[str, set[Any]]:
    return {
        "x": set(hints.get("x", set())),
        "z": set(hints.get("z", set())),
        "lab_start": set(hints.get("lab_start", set())),
        "combined_x": set(hints.get("combined_x", set())),
    }


def _update_solution_pool(
    pool: list[tuple[tuple[int, int], int, str, SolveResult, dict[str, set[Any]]]],
    *,
    seed: int,
    init_mode: str,
    result: SolveResult,
    hints: dict[str, set[Any]],
    top_k: int,
) -> None:
    pool.append((_score_for_pool(result), int(seed), str(init_mode), result, _clone_hints(hints)))
    pool.sort(key=lambda item: item[0])
    if len(pool) > int(top_k):
        del pool[top_k:]


def _run_dry_candidate_solve(
    *,
    run_id: Any,
    program_id: Any,
    academic_year_id: Any,
    candidate_seed: int,
    candidate_budget: float,
    enforce_teacher_load_limits: bool,
    require_optimal: bool,
    hybrid_init_enabled: bool,
    hybrid_population_size: int,
    hybrid_generations: int,
    initialization_mode: str,
    solve_deadline_monotonic: float | None = None,
) -> tuple[int, str, SolveResult]:
    db = SessionLocal()
    try:
        run = db.get(TimetableRun, run_id)
        if run is None:
            return (
                int(candidate_seed),
                str(initialization_mode),
                SolveResult(status="ERROR", entries_written=0, conflicts=[]),
            )

        bounded_budget = _cap_single_solve_budget_seconds(
            candidate_budget,
            deadline_monotonic=solve_deadline_monotonic,
        )
        if bounded_budget < MIN_BUDGET_SLICE_SECONDS:
            return (
                int(candidate_seed),
                str(initialization_mode),
                SolveResult(
                    status="ERROR",
                    entries_written=0,
                    conflicts=[],
                    message="Candidate solve skipped due to exhausted time budget.",
                ),
            )

        result = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=int(candidate_seed),
            max_time_seconds=float(bounded_budget),
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=False,
            clear_existing_entries=True,
            external_teacher_blocked_slot_ids=None,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            hints=None,
            initialization_mode=initialization_mode,
            persist_results=False,
            solve_deadline_monotonic=solve_deadline_monotonic,
        )
        return int(candidate_seed), str(initialization_mode), result
    finally:
        try:
            db.close()
        except Exception:
            pass


def _solve_program_with_restarts(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    academic_year_id,
    base_seed: int | None,
    max_time_seconds: float,
    enforce_teacher_load_limits: bool,
    require_optimal: bool,
    allow_extended_solve: bool,
    hybrid_init_enabled: bool,
    hybrid_population_size: int,
    hybrid_generations: int,
    num_restarts: int,
    lns_iterations: int,
    lns_keep_fraction: float,
    solve_deadline_monotonic: float | None = None,
) -> SolveResult:
    orchestration_started = time.monotonic()

    # Phase 1: multi-seed + multi-init candidate runs.
    num_restarts = min(MAX_RESTARTS, max(1, int(num_restarts or 1)))
    lns_iterations = min(MAX_ITERATIONS, max(0, int(lns_iterations or 0)))
    base_seed = int(base_seed) if base_seed is not None else 0

    remaining_at_start = _remaining_seconds(solve_deadline_monotonic)
    orchestration_budget = float(max_time_seconds)
    if remaining_at_start is not None:
        orchestration_budget = min(orchestration_budget, remaining_at_start)
    orchestration_budget = max(0.0, orchestration_budget)
    if orchestration_budget < MIN_BUDGET_SLICE_SECONDS:
        return SolveResult(
            status="ERROR",
            entries_written=0,
            conflicts=[],
            message="Solver deadline exceeded before restart orchestration could begin.",
        )

    phase1_budget_remaining = max(0.0, orchestration_budget * 0.35)
    phase2_budget_remaining = max(0.0, orchestration_budget * 0.25)
    phase_budget = (
        max(0.0, phase1_budget_remaining / max(1, num_restarts))
        if num_restarts > 0
        else 0.0
    )

    logger.info(
        "[solver] restart orchestration start: total_budget=%.1fs restarts=%d lns_iterations=%d",
        orchestration_budget,
        num_restarts,
        lns_iterations,
    )

    init_modes = build_initialization_modes(
        num_candidates=num_restarts,
        include_hybrid=bool(hybrid_init_enabled),
    )

    best_result: SolveResult | None = None
    best_seed: int = base_seed
    best_hints: dict[str, set[Any]] = {"x": set(), "z": set(), "lab_start": set(), "combined_x": set()}
    best_feedback: dict[str, Any] = {}
    strategy_scores: dict[str, float] = {}
    lns_telemetry_rows: list[dict[str, Any]] = []
    termination_reason = "COMPLETED"
    executed_restarts = 0
    executed_lns_iterations = 0

    # Solution pool keeps top candidates to avoid losing strong schedules.
    solution_pool: list[tuple[tuple[int, int], int, str, SolveResult, dict[str, set[Any]]]] = []
    top_k = min(5, num_restarts + max(0, int(lns_iterations or 0)))

    # Sequential execution is intentionally used to keep CPU and wall-time
    # predictable under strict runtime limits.
    for idx in range(num_restarts):
        if _is_deadline_exceeded(solve_deadline_monotonic):
            termination_reason = "GLOBAL_TIME_LIMIT_REACHED_PHASE1"
            break

        candidate_seed = base_seed + idx + 1
        init_mode = init_modes[idx % len(init_modes)]

        candidate_budget = min(phase_budget, phase1_budget_remaining)
        candidate_budget = _cap_single_solve_budget_seconds(
            candidate_budget,
            deadline_monotonic=solve_deadline_monotonic,
        )
        if candidate_budget < MIN_BUDGET_SLICE_SECONDS:
            termination_reason = "INSUFFICIENT_PHASE1_BUDGET"
            break

        candidate = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=candidate_seed,
            max_time_seconds=candidate_budget,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=False,
            clear_existing_entries=True,
            external_teacher_blocked_slot_ids=None,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            hints=None,
            initialization_mode=init_mode,
            persist_results=False,
            solve_deadline_monotonic=solve_deadline_monotonic,
        )
        executed_restarts += 1
        phase1_budget_remaining = max(0.0, phase1_budget_remaining - float(candidate.solve_time_seconds or 0.0))

        candidate_hints = getattr(candidate, "solution_hints", {}) or {}
        _update_solution_pool(
            solution_pool,
            seed=candidate_seed,
            init_mode=init_mode,
            result=candidate,
            hints=candidate_hints,
            top_k=top_k,
        )
        if _is_better_solution(candidate, best_result):
            best_result = candidate
            best_seed = candidate_seed
            best_hints = _clone_hints(candidate_hints)
            best_feedback = dict(getattr(candidate, "lns_feedback", {}) or {})

    if best_result is None or not _is_feasible_status(best_result.status):
        # Fallback: run single solve and persist result.
        fallback_budget = _cap_single_solve_budget_seconds(
            max_time_seconds,
            deadline_monotonic=solve_deadline_monotonic,
        )
        if fallback_budget < MIN_BUDGET_SLICE_SECONDS:
            return SolveResult(
                status="ERROR",
                entries_written=0,
                conflicts=[],
                message="No budget left for fallback solve after restart candidates.",
            )
        return _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=base_seed,
            max_time_seconds=fallback_budget,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            clear_existing_entries=True,
            external_teacher_blocked_slot_ids=None,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            hints=None,
            initialization_mode="heuristic",
            persist_results=True,
            solve_deadline_monotonic=solve_deadline_monotonic,
        )

    # Phase 2: adaptive LNS improvement rounds over the current best.
    for lns_idx in range(lns_iterations):
        if _is_deadline_exceeded(solve_deadline_monotonic):
            termination_reason = "GLOBAL_TIME_LIMIT_REACHED_PHASE2"
            break

        iter_left = max(1, lns_iterations - lns_idx)
        lns_budget = phase2_budget_remaining / float(iter_left)
        lns_budget = _cap_single_solve_budget_seconds(
            lns_budget,
            deadline_monotonic=solve_deadline_monotonic,
        )
        if lns_budget < MIN_BUDGET_SLICE_SECONDS:
            termination_reason = "INSUFFICIENT_PHASE2_BUDGET"
            break

        lns_strategy = choose_lns_strategy(
            lns_idx,
            feedback=best_feedback,
            strategy_scores=strategy_scores,
            seed=base_seed,
        )
        lns_hints = build_lns_hints(
            best_hints,
            keep_fraction=lns_keep_fraction,
            seed=base_seed + lns_idx + 100,
            strategy=lns_strategy,
            feedback=best_feedback,
        )
        lns_hints = run_hybrid_repair_loop(
            candidate_hints=lns_hints,
            iterations=1,
            deadline_monotonic=solve_deadline_monotonic,
        )
        candidate = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=best_seed + lns_idx + 1,
            max_time_seconds=lns_budget,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=False,
            clear_existing_entries=True,
            external_teacher_blocked_slot_ids=None,
            hybrid_init_enabled=False,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
            hints=lns_hints,
            initialization_mode=None,
            persist_results=False,
            solve_deadline_monotonic=solve_deadline_monotonic,
        )
        executed_lns_iterations += 1
        phase2_budget_remaining = max(0.0, phase2_budget_remaining - float(candidate.solve_time_seconds or 0.0))

        candidate_hints = getattr(candidate, "solution_hints", {}) or {}
        _update_solution_pool(
            solution_pool,
            seed=best_seed + lns_idx + 1,
            init_mode=f"lns:{lns_strategy}",
            result=candidate,
            hints=candidate_hints,
            top_k=top_k,
        )

        # Online strategy gain update from objective improvements.
        baseline = int(best_result.objective_score) if (best_result and best_result.objective_score is not None) else None
        cand_obj = int(candidate.objective_score) if candidate.objective_score is not None else None
        raw_gain = 0
        if baseline is not None and cand_obj is not None:
            raw_gain = max(0, baseline - cand_obj)
            prev = float(strategy_scores.get(lns_strategy, 0.0))
            # EMA to stabilize noisy per-iteration gains.
            strategy_scores[lns_strategy] = (0.7 * prev) + (0.3 * float(raw_gain))

        accepted = bool(_is_better_solution(candidate, best_result))
        lns_telemetry_rows.append(
            {
                "iteration": int(lns_idx + 1),
                "strategy": str(lns_strategy),
                "seed": int(best_seed + lns_idx + 1),
                "baseline_objective": baseline,
                "candidate_objective": cand_obj,
                "objective_gain": int(raw_gain),
                "ema_score": float(strategy_scores.get(lns_strategy, 0.0)),
                "accepted": accepted,
                "status": str(candidate.status),
            }
        )

        if accepted:
            best_result = candidate
            best_seed = best_seed + lns_idx + 1
            best_hints = _clone_hints(candidate_hints)
            best_feedback = dict(getattr(candidate, "lns_feedback", {}) or {})

    if solution_pool:
        _score, pool_seed, _mode, pool_result, pool_hints = solution_pool[0]
        if _is_better_solution(pool_result, best_result):
            best_result = pool_result
            best_seed = int(pool_seed)
            best_hints = _clone_hints(pool_hints)
            best_feedback = dict(getattr(pool_result, "lns_feedback", {}) or {})

    pool_summary: list[dict[str, Any]] = []
    for _score, pool_seed, pool_mode, pool_result, _pool_hints in solution_pool:
        pool_summary.append(
            {
                "seed": int(pool_seed),
                "mode": str(pool_mode),
                "status": str(pool_result.status),
                "objective": (
                    int(pool_result.objective_score)
                    if pool_result.objective_score is not None
                    else None
                ),
            }
        )

    # Phase 3: Final best solution persisted
    final_budget = _cap_single_solve_budget_seconds(
        max_time_seconds,
        deadline_monotonic=solve_deadline_monotonic,
    )
    if final_budget < MIN_BUDGET_SLICE_SECONDS:
        telemetry_payload = {
            "multi_start_count": int(num_restarts),
            "multi_start_executed": int(executed_restarts),
            "lns_iterations_requested": int(lns_iterations),
            "lns_iterations_executed": int(executed_lns_iterations),
            "strategy_scores": {k: float(v) for k, v in strategy_scores.items()},
            "lns_iterations": lns_telemetry_rows,
            "solution_pool": pool_summary,
            "selected_seed": int(best_seed),
            "termination_reason": "NO_BUDGET_FOR_FINAL_PERSIST",
            "wall_time_seconds": float(round(time.monotonic() - orchestration_started, 3)),
        }
        return SolveResult(
            status="ERROR",
            entries_written=0,
            conflicts=[],
            objective_score=getattr(best_result, "objective_score", None),
            warnings=[
                *list(getattr(best_result, "warnings", []) or []),
                "No remaining time budget to persist the final solution.",
            ],
            solver_stats={"lns_telemetry": telemetry_payload},
            message="Solver found candidate schedules but exhausted time before final persistence.",
        )

    final_result = _solve_program(
        db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        seed=best_seed,
        max_time_seconds=final_budget,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        allow_extended_solve=allow_extended_solve,
        clear_existing_entries=True,
        external_teacher_blocked_slot_ids=None,
        hybrid_init_enabled=False,
        hybrid_population_size=hybrid_population_size,
        hybrid_generations=hybrid_generations,
        hints=best_hints,
        initialization_mode=None,
        persist_results=True,
        solve_deadline_monotonic=solve_deadline_monotonic,
    )

    telemetry_payload = {
        "multi_start_count": int(num_restarts),
        "multi_start_executed": int(executed_restarts),
        "lns_iterations_requested": int(lns_iterations),
        "lns_iterations_executed": int(executed_lns_iterations),
        "strategy_scores": {k: float(v) for k, v in strategy_scores.items()},
        "lns_iterations": lns_telemetry_rows,
        "solution_pool": pool_summary,
        "selected_seed": int(best_seed),
        "termination_reason": str(termination_reason),
        "wall_time_seconds": float(round(time.monotonic() - orchestration_started, 3)),
        "hard_total_time_limit_seconds": float(HARD_TOTAL_SOLVE_LIMIT_SECONDS),
    }

    try:
        final_result.solver_stats = dict(final_result.solver_stats or {})
        final_result.solver_stats["lns_telemetry"] = telemetry_payload
    except Exception:
        pass

    try:
        run.parameters = {
            **(run.parameters or {}),
            "_lns_telemetry": telemetry_payload,
        }
        db.add(run)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # Phase 5: Final safety check - ensure we never exceeded deadline
    if _is_deadline_exceeded(solve_deadline_monotonic):
        logger.warning(
            "[solver] CRITICAL: reached return point AFTER deadline exceeded. "
            "This indicates a deadline breach. Forcing termination."
        )
        termination_reason = "DEADLINE_BREACH_AT_END"
        final_result = final_result or SolveResult(
            status="TIMEOUT",
            entries_written=0,
            conflicts=[],
            message="Solver completed after deadline breach detection.",
        )

    logger.info(
        "[solver] restart orchestration end: reason=%s restarts=%d/%d lns=%d/%d",
        termination_reason,
        executed_restarts,
        num_restarts,
        executed_lns_iterations,
        lns_iterations,
    )

    return final_result


def _timeout_result(
    *,
    db: Session,
    run: TimetableRun,
    tenant_id: Any | None,
    persist_results: bool,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> SolveResult:
    conflict = TimetableConflict(
        tenant_id=tenant_id,
        run_id=run.id,
        severity="ERROR",
        conflict_type="TIMEOUT",
        message=message,
        metadata_json=dict(metadata or {}),
    )

    if persist_results:
        try:
            run.status = "ERROR"
            run.notes = str(message)[:500]
            db.add(conflict)
            db.add(run)
            db.commit()
            return SolveResult(
                status="ERROR",
                entries_written=0,
                conflicts=[conflict],
                message=message,
            )
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    return SolveResult(
        status="ERROR",
        entries_written=0,
        conflicts=[],
        message=message,
    )


def _solve_program(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    academic_year_id,
    section_id_subset: set[Any] | None = None,
    seed: int | None,
    max_time_seconds: float,
    enforce_teacher_load_limits: bool,
    require_optimal: bool,
    allow_extended_solve: bool = False,
    clear_existing_entries: bool = True,
    external_teacher_blocked_slot_ids: dict[Any, set[Any]] | None = None,
    hybrid_init_enabled: bool = False,
    hybrid_population_size: int = 24,
    hybrid_generations: int = 20,
    hints: dict[str, set[Any]] | None = None,
    initialization_mode: str | None = None,
    persist_results: bool = True,
    suppress_terminal_status_update: bool = False,
    solve_deadline_monotonic: float | None = None,
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)
    solve_wall_started = time.monotonic()
    effective_budget = _cap_single_solve_budget_seconds(
        max_time_seconds,
        deadline_monotonic=solve_deadline_monotonic,
    )
    if effective_budget < MIN_BUDGET_SLICE_SECONDS:
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before model build: no remaining time budget.",
            metadata={
                "phase": "pre_model",
                "requested_seconds": float(max_time_seconds),
                "effective_seconds": float(effective_budget),
            },
        )

    # 1. Build context
    ctx = SolverContext(
        db=db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        section_id_subset=section_id_subset,
        seed=seed,
        max_time_seconds=effective_budget,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        tenant_id=tenant_id,
    )
    if external_teacher_blocked_slot_ids:
        for teacher_id, slot_ids in external_teacher_blocked_slot_ids.items():
            if slot_ids:
                ctx.external_teacher_blocked_slot_ids[teacher_id].update(slot_ids)

    # 2. Load data
    if _is_deadline_exceeded(solve_deadline_monotonic):
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before data load: strict time limit reached.",
            metadata={"phase": "load_all"},
        )
    load_all(ctx)

    # 3. Pre-solve locks (special allotments, fixed entries, teacher pruning)
    apply_pre_solve_locks(ctx)

    # 3a. PHASE 9: Validate pre-solve locks are safe and don't over-constrain the model
    lock_warnings = validate_pre_solve_locks(ctx)
    if lock_warnings:
        ctx.warnings.extend(lock_warnings)

    # 3b. OPTIMIZATION: build per-(section,subject) pruned slot lists.
    #     Must run AFTER apply_pre_solve_locks so teacher_disallowed_slot_ids
    #     is fully populated.  Variables step reads these lists directly.
    build_pruned_slots(ctx)

    # 3b-II. PHASE 7: Validate domain reduction effectiveness and warn on
    #         likely infeasibility indicators (empty slot sets, no compatible rooms).
    _validate_domain_reduction(ctx)

    # 3c. Validate teacher time-window feasibility.  Collect warnings for
    #     any (teacher, section) pair where the intersection of the teacher
    #     window and the section window is empty.  These are surfaced in the
    #     SolveResult so the frontend can show a clear message, but we do NOT
    #     abort the solve — the infeasible pair will simply produce no
    #     variables and the solver will report INFEASIBLE naturally.
    tw_warnings = check_teacher_window_feasibility(ctx)
    for w in tw_warnings:
        logger.warning("[solver] teacher-window feasibility: %s", w)
    if tw_warnings:
        ctx.warnings.extend(tw_warnings)

    # 3d. Validate subject allowed-room configurations.  Warn when a subject's
    #     allowed rooms list exists but contains no rooms compatible with the
    #     subject type (e.g. a LAB subject restricted to a CLASSROOM room).
    sar_warnings = _check_subject_allowed_rooms(ctx)
    for w in sar_warnings:
        logger.warning("[solver] subject-allowed-rooms: %s", w)
    if sar_warnings:
        ctx.warnings.extend(sar_warnings)

    # 4. Create CP-SAT variables
    if _is_deadline_exceeded(solve_deadline_monotonic):
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before variable creation: strict time limit reached.",
            metadata={"phase": "create_variables"},
        )
    create_variables(ctx)

    # 5. Add constraints
    if _is_deadline_exceeded(solve_deadline_monotonic):
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before constraint build: strict time limit reached.",
            metadata={"phase": "add_constraints"},
        )
    add_constraints(ctx)

    # 6. Set objective
    if _is_deadline_exceeded(solve_deadline_monotonic):
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before objective build: strict time limit reached.",
            metadata={"phase": "add_objective"},
        )
    add_objective(ctx)

    # 6b. Optional hybrid initialization (GA-style warm hints).
    if hybrid_init_enabled:
        try:
            hybrid_hints = generate_hybrid_hints(
                ctx,
                seed=seed,
                population_size=int(hybrid_population_size),
                generations=int(hybrid_generations),
            )
            for var, val in hybrid_hints.items():
                ctx.model.AddHint(var, int(val))
            logger.info("[solver] hybrid hints applied: %d", len(hybrid_hints))
        except Exception:
            logger.warning("[solver] hybrid initialization failed; continuing without hints", exc_info=True)

    if initialization_mode:
        try:
            init_hints = generate_initial_hints(
                ctx,
                mode=initialization_mode,
                seed=seed,
                hybrid_population_size=int(hybrid_population_size),
                hybrid_generations=int(hybrid_generations),
                deadline_monotonic=solve_deadline_monotonic,
            )
            if not hints:
                hints = init_hints
            else:
                for family in ("x", "z", "lab_start", "combined_x"):
                    hints.setdefault(family, set()).update(init_hints.get(family, set()))
            logger.info(
                "[solver] initialization mode=%s hints=(x=%d,z=%d,lab=%d,combined=%d)",
                initialization_mode,
                len((hints or {}).get("x", set())),
                len((hints or {}).get("z", set())),
                len((hints or {}).get("lab_start", set())),
                len((hints or {}).get("combined_x", set())),
            )
        except Exception:
            logger.warning("[solver] initialization mode failed; continuing", exc_info=True)

    # 7. Apply initial warm-start hints (for multi-seed / LNS workflows).
    if hints:
        # Accept structured hints from _extract_solution_hints/_lns_hints_from_best.
        for var_key in hints.get("x", []):
            var = ctx.x.get(var_key)
            if var is not None:
                try:
                    ctx.model.AddHint(var, 1)
                except Exception:
                    pass
        for var_key in hints.get("z", []):
            var = ctx.z.get(var_key)
            if var is not None:
                try:
                    ctx.model.AddHint(var, 1)
                except Exception:
                    pass
        for var_key in hints.get("lab_start", []):
            var = ctx.lab_start.get(var_key)
            if var is not None:
                try:
                    ctx.model.AddHint(var, 1)
                except Exception:
                    pass
        for var_key in hints.get("combined_x", []):
            var = ctx.combined_x.get(var_key)
            if var is not None:
                try:
                    ctx.model.AddHint(var, 1)
                except Exception:
                    pass

    # 8. Search strategy hints — guide CP-SAT to branch on the most
    #    constrained decision variables first (section-slot assignments).
    _add_search_hints(ctx)

    # 9. Solve
    num_vars = len(ctx.model.Proto().variables)
    num_constraints = len(ctx.model.Proto().constraints)
    slots_total = sum(len(v) for v in ctx.valid_slots_by_section_subject.values())
    combined_slots_total = sum(len(v) for v in ctx.valid_slots_for_combined_group.values())
    elective_slots_total = sum(len(v) for v in ctx.valid_slots_for_elective_batch.values())
    ctx.pre_solve_metrics = {
        "num_vars": num_vars,
        "num_constraints": num_constraints,
        "pruned_slots_total": slots_total,
        "combined_slots_total": combined_slots_total,
        "elective_slots_total": elective_slots_total,
        "sections": len(ctx.sections),
        "teachers": len(ctx.teachers),
    }
    logger.info(
        "[solver] pre-solve: vars=%d constraints=%d pruned_slots=%d combined_slots=%d elective_slots=%d sections=%d teachers=%d",
        num_vars, num_constraints, slots_total, combined_slots_total, elective_slots_total,
        ctx.pre_solve_metrics["sections"], ctx.pre_solve_metrics["teachers"],
    )
    # Structured stats block for operators.
    logger.info(
        "[solver] === Solver Stats ===\n"
        "          Sections:    %d\n"
        "          Subjects:    %d\n"
        "          Slots:       %d\n"
        "          Variables:   %s\n"
        "          Constraints: %s\n"
        "          ===================",
        len(ctx.sections),
        len(ctx.subjects),
        len(ctx.slots),
        f"{num_vars:,}",
        f"{num_constraints:,}",
    )

    # Adaptive solve budget: scale by model size while respecting hard caps.
    requested_cap = _cap_single_solve_budget_seconds(
        effective_budget,
        deadline_monotonic=solve_deadline_monotonic,
    )
    if requested_cap < MIN_BUDGET_SLICE_SECONDS:
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before CP-SAT call: no remaining runtime budget.",
            metadata={"phase": "solve_precheck"},
        )

    initial_budget = _estimate_adaptive_budget_seconds(
        requested_cap=requested_cap,
        num_vars=num_vars,
        num_constraints=num_constraints,
        sections=len(ctx.sections),
        teachers=len(ctx.teachers),
        slots=len(ctx.slots),
        require_optimal=bool(require_optimal),
    )
    initial_budget = _cap_single_solve_budget_seconds(
        initial_budget,
        deadline_monotonic=solve_deadline_monotonic,
    )
    if initial_budget < MIN_BUDGET_SLICE_SECONDS:
        return _timeout_result(
            db=db,
            run=run,
            tenant_id=tenant_id,
            persist_results=persist_results,
            message="Solver aborted before CP-SAT call: adaptive budget collapsed to zero.",
            metadata={"phase": "solve_budget"},
        )

    solver_seed = int(seed) if seed is not None else int(DEFAULT_RANDOM_SEED)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = initial_budget
    solver.parameters.max_deterministic_time = initial_budget
    solver.parameters.num_search_workers = int(DEFAULT_NUM_SEARCH_WORKERS)
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_presolve = True
    solver.parameters.symmetry_level = 2
    solver.parameters.randomize_search = True
    solver.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
    solver.parameters.log_search_progress = True
    solver.parameters.random_seed = solver_seed
    if hasattr(solver.parameters, "max_number_of_conflicts"):
        solver.parameters.max_number_of_conflicts = int(DEFAULT_MAX_CONFLICTS)

    logger.info(
        "[solver] starting solve: requested_cap=%.1fs adaptive_budget=%.1fs deterministic_cap=%.1fs workers=%d seed=%d extended_solve=%s",
        requested_cap,
        initial_budget,
        initial_budget,
        solver.parameters.num_search_workers,
        solver_seed,
        allow_extended_solve,
    )

    status = solver.Solve(ctx.model)
    termination_reason = {
        cp_model.OPTIMAL: "OPTIMAL_FOUND",
        cp_model.FEASIBLE: "FEASIBLE_FOUND",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "TIME_LIMIT_OR_UNKNOWN",
    }.get(status, "SOLVER_STATUS_OTHER")

    # Extended solve: if FEASIBLE (not proven optimal) and the caller opted in,
    # re-run only within remaining budget from this pass.
    if allow_extended_solve and status == cp_model.FEASIBLE:
        already_spent = float(solver.WallTime() or 0.0)
        extra_budget = _cap_single_solve_budget_seconds(
            max(0.0, requested_cap - already_spent),
            deadline_monotonic=solve_deadline_monotonic,
        )
        if extra_budget >= MIN_BUDGET_SLICE_SECONDS:
            logger.info(
                "[solver] status=FEASIBLE, launching focused improve pass: extra_budget=%.1fs",
                extra_budget,
            )
            solver.parameters.max_time_in_seconds = extra_budget
            solver.parameters.max_deterministic_time = extra_budget
            solver.parameters.randomize_search = True
            solver.parameters.random_seed = int(solver_seed) + 97
            status = solver.Solve(ctx.model)
            termination_reason = {
                cp_model.OPTIMAL: "EXTENDED_PASS_OPTIMAL",
                cp_model.FEASIBLE: "EXTENDED_PASS_FEASIBLE",
                cp_model.INFEASIBLE: "EXTENDED_PASS_INFEASIBLE",
                cp_model.UNKNOWN: "EXTENDED_PASS_TIMEOUT_OR_UNKNOWN",
            }.get(status, "EXTENDED_PASS_OTHER")
            logger.info(
                "[solver] focused improve pass finished: status=%s wall_time=%.1fs",
                {0: "UNKNOWN", 2: "FEASIBLE", 3: "INFEASIBLE", 4: "OPTIMAL"}.get(int(status), str(status)),
                solver.WallTime(),
            )
        else:
            logger.info("[solver] skipping focused improve pass: no remaining budget")

    logger.info(
        "[solver] solve complete: status=%s wall_time=%.1fs termination_reason=%s total_wall_elapsed=%.1fs",
        {0: "UNKNOWN", 2: "FEASIBLE", 3: "INFEASIBLE", 4: "OPTIMAL"}.get(int(status), str(status)),
        solver.WallTime(),
        termination_reason,
        max(0.0, time.monotonic() - solve_wall_started),
    )
    setattr(ctx, "_termination_reason", str(termination_reason))

    # 9. Handle infeasible / error
    # CP-SAT may return UNKNOWN on time limit even when an incumbent solution
    # exists. In that case, promote to FEASIBLE so result writing can persist
    # a valid timetable instead of returning a generic ERROR.
    if status == cp_model.UNKNOWN:
        has_incumbent_solution = False
        try:
            has_incumbent_solution = len(solver.ResponseProto().solution) > 0
        except Exception:
            has_incumbent_solution = False
        if has_incumbent_solution:
            logger.warning("[solver] status=UNKNOWN with incumbent solution; promoting to FEASIBLE")
            status = cp_model.FEASIBLE

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _handle_infeasible(
            ctx, solver, status,
            persist_results=persist_results,
            deadline_monotonic=solve_deadline_monotonic,
        )

    # 10. Build interim result values for dry-run vs persisted paths.
    if not persist_results:
        objective_score = None
        best_objective_bound = None
        optimality_gap = None
        solve_time_seconds = None

        try:
            objective_score = int(solver.ObjectiveValue())
        except Exception:
            pass
        try:
            best_objective_bound = int(solver.BestObjectiveBound())
            if objective_score is not None:
                optimality_gap = max(0, objective_score - best_objective_bound)
        except Exception:
            pass
        try:
            solve_time_seconds = float(solver.WallTime())
        except Exception:
            pass

        # Compute warnings and stats consistent with persisted solver path.
        from solver.result_writer import _compute_warnings, _compute_solver_stats

        _compute_warnings(ctx, solver)
        _compute_solver_stats(ctx, solver, status)
        ctx.solver_stats["termination_reason"] = str(termination_reason)
        ctx.solver_stats["hard_single_solve_limit_seconds"] = float(HARD_SINGLE_SOLVE_LIMIT_SECONDS)
        ctx.solver_stats["hard_total_solve_limit_seconds"] = float(HARD_TOTAL_SOLVE_LIMIT_SECONDS)

        hints_out = _extract_solution_hints(ctx, solver)
        lns_feedback = _build_lns_feedback(ctx, hints_out, solver, deadline_monotonic=solve_deadline_monotonic)

        return SolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            entries_written=0,
            conflicts=[],
            objective_score=objective_score,
            warnings=ctx.warnings,
            solver_stats=ctx.solver_stats,
            best_objective_bound=best_objective_bound,
            optimality_gap=optimality_gap,
            solve_time_seconds=solve_time_seconds,
            message=ctx.message,
            solution_hints=hints_out,
            lns_feedback=lns_feedback,
        )

    # 10. Write results
    return write_results(
        ctx,
        solver,
        status,
        clear_existing_entries=clear_existing_entries,
        suppress_terminal_status_update=suppress_terminal_status_update,
    )


def _add_search_hints(ctx: SolverContext) -> None:
    """Add decision strategy hints to guide CP-SAT branching.

    Hints the solver to:
    1. Branch on section-slot variables first (most constrained)
    2. Prefer assigning variables to 1 (commit early)

    This typically improves time-to-first-solution significantly.
    """
    # Collect all primary decision variables
    hint_vars = []

    # Theory variables — most constrained first
    hint_vars.extend(ctx.x.values())

    # Lab start variables
    hint_vars.extend(ctx.lab_start.values())

    # Combined THEORY variables
    hint_vars.extend(ctx.combined_x.values())

    # Elective block variables
    hint_vars.extend(ctx.z.values())

    if hint_vars:
        ctx.model.AddDecisionStrategy(
            hint_vars,
            cp_model.CHOOSE_FIRST,          # pick first unassigned var
            cp_model.SELECT_MAX_VALUE,       # try value 1 first (commit)
        )


def _handle_infeasible(
    ctx: SolverContext,
    solver: cp_model.CpSolver,
    status: int,
    *,
    persist_results: bool = True,
    deadline_monotonic: float | None = None,
) -> SolveResult:
    """Handle non-feasible solver outcomes.
    
    If CP-SAT returns INFEASIBLE, attempt greedy fallback before giving up.
    
    PHASE 8 ENHANCEMENT: Added deadline parameter. Diagnostics skipped if
    near deadline to prevent blocking on INFEASIBLE analysis.
    """
    ortools_status = int(status)
    diagnostics: list[dict] = []
    reason_summary: str | None = None
    tenant_id = ctx.tenant_id
    run = ctx.run

    if status == cp_model.INFEASIBLE:
        # Try greedy fallback before marking as truly infeasible
        logger.info("CP-SAT returned INFEASIBLE; attempting greedy fallback solver...")
        try:
            from solver.greedy_solver import greedy_fallback_solver
            greedy_result = greedy_fallback_solver(ctx)
            logger.info(f"Greedy fallback succeeded with {greedy_result.entries_written} entries")
            return greedy_result
        except Exception as e:
            logger.exception(f"Greedy fallback failed: {e}")
            # Fall through to standard INFEASIBLE handling
        
        run.status = "INFEASIBLE"
        conflict_type = "INFEASIBLE"
        message = (
            "Solver infeasible due to special locked allotments (greedy fallback also failed)."
            if ctx.special_allotments
            else "Solver could not find a feasible timetable (greedy fallback also failed)."
        )

        # Phase 8: Skip diagnostics if near deadline (non-blocking)
        skip_diagnostics = False
        if deadline_monotonic is not None:
            remaining = max(0.0, deadline_monotonic - time.monotonic())
            if remaining <= MIN_BUDGET_SLICE_SECONDS:
                logger.info("[solver] Skipping INFEASIBLE diagnostics due to deadline pressure (Phase 8)")
                skip_diagnostics = True

        if not skip_diagnostics:
            try:
                from solver.solver_diagnostics import run_infeasibility_analysis, summarize_diagnostics

                diagnostics = run_infeasibility_analysis(
                    {
                        "sections": ctx.sections,
                        "section_required": ctx.section_required,
                        "assigned_teacher_by_section_subject": ctx.assigned_teacher_by_section_subject,
                        "subject_by_id": ctx.subject_by_id,
                        "teacher_by_id": ctx.teacher_by_id,
                        "slots": ctx.slots,
                        "slot_info": ctx.slot_info,
                        "slot_by_day_index": ctx.slot_by_day_index,
                        "windows_by_section": ctx.windows_by_section,
                        "fixed_entries": ctx.fixed_entries,
                        "special_allotments": ctx.special_allotments,
                        "group_sections": ctx.group_sections,
                        "group_subject": ctx.group_subject,
                        "blocks_by_section": ctx.blocks_by_section,
                        "block_subject_pairs_by_block": ctx.block_subject_pairs_by_block,
                        "rooms_by_type": ctx.rooms_by_type,
                        "room_by_id": ctx.room_by_id,
                        "teacher_disallowed_slot_ids": ctx.teacher_disallowed_slot_ids,
                        "external_teacher_blocked_slot_ids": ctx.external_teacher_blocked_slot_ids,
                        "valid_slots_by_section_subject": ctx.valid_slots_by_section_subject,
                        "valid_slots_for_combined_group": ctx.valid_slots_for_combined_group,
                        "valid_slots_for_elective_batch": ctx.valid_slots_for_elective_batch,
                    }
                )
                reason_summary = summarize_diagnostics(diagnostics)
            except Exception:
                diagnostics = []
                reason_summary = None
    elif status == cp_model.UNKNOWN:
        run.status = "ERROR"
        conflict_type = "TIMEOUT"
        message = (
            "Solver timed out without finding a feasible timetable. "
            "Increase max_time_seconds or relax constraints."
        )
    elif hasattr(cp_model, "MODEL_INVALID") and status == cp_model.MODEL_INVALID:
        run.status = "ERROR"
        conflict_type = "MODEL_INVALID"
        message = "Solver model invalid. Check input data and constraints."
    else:
        run.status = "ERROR"
        conflict_type = "SOLVER_ERROR"
        message = "Solver returned an unexpected status."

    conflict = TimetableConflict(
        tenant_id=tenant_id,
        run_id=run.id,
        severity="ERROR",
        conflict_type=conflict_type,
        message=message,
        metadata_json={
            "ortools_status": ortools_status,
            **({"reason_summary": reason_summary} if reason_summary else {}),
            **({"diagnostics": diagnostics} if diagnostics else {}),
        },
    )
    if persist_results:
        ctx.db.add(conflict)
        ctx.db.commit()
        return SolveResult(
            status=str(run.status),
            entries_written=0,
            conflicts=[conflict],
            diagnostics=diagnostics,
            reason_summary=reason_summary,
        )

    return SolveResult(
        status=str(run.status),
        entries_written=0,
        conflicts=[],
        diagnostics=diagnostics,
        reason_summary=reason_summary,
    )
