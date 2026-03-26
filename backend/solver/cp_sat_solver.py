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

from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model
from sqlalchemy import select
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
import os

from solver.constraints import add_constraints
from solver.data_loader import load_all, build_pruned_slots
from solver.hybrid_loop import run_hybrid_repair_loop
from solver.hybrid_initializer import generate_hybrid_hints
from solver.initialization_engine import build_initialization_modes, generate_initial_hints
from solver.lns_strategies import build_lns_hints, choose_lns_strategy
from solver.objective import add_objective
from solver.pre_solve_locks import apply_pre_solve_locks, check_teacher_window_feasibility
from solver.result_writer import write_results
from solver.variables import create_variables

logger = logging.getLogger(__name__)


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
    adaptive = 45.0 + (complexity / 180.0)
    if require_optimal:
        adaptive *= 1.2
    adaptive = max(45.0, min(float(requested_cap), adaptive))
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
    if multi_seed_restarts <= 1 and lns_iterations <= 0:
        return _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=seed,
            max_time_seconds=max_time_seconds,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
        )

    return _solve_program_with_restarts(
        db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        base_seed=seed,
        max_time_seconds=max_time_seconds,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        allow_extended_solve=allow_extended_solve,
        hybrid_init_enabled=hybrid_init_enabled,
        hybrid_population_size=hybrid_population_size,
        hybrid_generations=hybrid_generations,
        num_restarts=multi_seed_restarts,
        lns_iterations=lns_iterations,
        lns_keep_fraction=lns_keep_fraction,
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
    return _solve_program_global_decomposed(
        db,
        run=run,
        program_id=program_id,
        seed=seed,
        max_time_seconds=max_time_seconds,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        allow_extended_solve=allow_extended_solve,
        hybrid_init_enabled=hybrid_init_enabled,
        hybrid_population_size=hybrid_population_size,
        hybrid_generations=hybrid_generations,
        multi_seed_restarts=multi_seed_restarts,
        lns_iterations=lns_iterations,
        lns_keep_fraction=lns_keep_fraction,
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
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)

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
            max_time_seconds=max_time_seconds,
            enforce_teacher_load_limits=enforce_teacher_load_limits,
            require_optimal=require_optimal,
            allow_extended_solve=allow_extended_solve,
            hybrid_init_enabled=hybrid_init_enabled,
            hybrid_population_size=hybrid_population_size,
            hybrid_generations=hybrid_generations,
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
        remaining_units = batch_units[idx:]
        remaining_weight = float(sum(max(1, len(sec_ids)) for _yid, sec_ids in remaining_units))
        this_weight = float(max(1, len(section_subset)))
        proportional_budget = remaining_budget * (this_weight / max(1.0, remaining_weight))
        batch_budget = min(300.0, max(45.0, proportional_budget))
        if require_optimal:
            batch_budget = min(300.0, max(90.0, batch_budget))

        logger.info(
            "[solver] global decomposed batch=%d/%d year_id=%s budget=%.1fs sections_in_batch=%d blocked_teachers=%d",
            idx + 1,
            len(batch_units),
            str(year_id),
            batch_budget,
            len(section_subset),
            len(teacher_schedule_map),
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
        )
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
        remaining_budget = max(45.0, remaining_budget - elapsed)

        if str(result.status) in {"INFEASIBLE", "ERROR", "VALIDATION_FAILED"}:
            break

    if last_result is None:
        return SolveResult(status="ERROR", entries_written=0, conflicts=[])

    return SolveResult(
        status=str(last_result.status),
        entries_written=total_entries_written,
        conflicts=combined_conflicts,
        diagnostics=list(last_result.diagnostics or []),
        reason_summary=last_result.reason_summary,
        objective_score=last_result.objective_score,
        warnings=total_warnings,
        solver_stats=dict(last_result.solver_stats or {}),
        best_objective_bound=last_result.best_objective_bound,
        optimality_gap=last_result.optimality_gap,
        solve_time_seconds=last_result.solve_time_seconds,
        message=last_result.message,
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
) -> dict[str, Any]:
    teacher_load: dict[Any, int] = defaultdict(int)
    section_load: dict[Any, int] = defaultdict(int)
    x_keys_by_teacher: dict[Any, list[Any]] = defaultdict(list)
    x_keys_by_section: dict[Any, list[Any]] = defaultdict(list)
    high_penalty_x_keys: list[Any] = []

    for key in solution_hints.get("x", set()):
        sec_id, subj_id, slot_id = key
        teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
        if teacher_id is not None:
            teacher_load[teacher_id] += 1
            x_keys_by_teacher[teacher_id].append(key)
        section_load[sec_id] += 1
        x_keys_by_section[sec_id].append(key)

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

    return {
        "teacher_hotspots": teacher_hotspots,
        "section_hotspots": section_hotspots,
        "teacher_penalty_score": dict(teacher_penalty_score),
        "section_penalty_score": dict(section_penalty_score),
        "x_keys_by_teacher": {k: list(v) for k, v in x_keys_by_teacher.items()},
        "x_keys_by_section": {k: list(v) for k, v in x_keys_by_section.items()},
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

        result = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=int(candidate_seed),
            max_time_seconds=float(candidate_budget),
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
) -> SolveResult:
    # Phase 1: multi-seed + multi-init candidate runs.
    num_restarts = max(1, int(num_restarts or 1))
    base_seed = int(base_seed) if base_seed is not None else 0
    initial_budget = min(max_time_seconds * 0.4, max(8.0, max_time_seconds * 0.4))
    phase_budget = max(10.0, initial_budget / num_restarts)

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

    # Solution pool keeps top candidates to avoid losing strong schedules.
    solution_pool: list[tuple[tuple[int, int], int, str, SolveResult, dict[str, set[Any]]]] = []
    top_k = min(5, num_restarts + max(0, int(lns_iterations or 0)))

    worker_count = min(num_restarts, max(1, ((os.cpu_count() or 4) // 2)))
    if num_restarts == 1 or worker_count <= 1:
        for idx in range(num_restarts):
            candidate_seed = base_seed + idx + 1
            init_mode = init_modes[idx % len(init_modes)]
            candidate = _solve_program(
                db,
                run=run,
                program_id=program_id,
                academic_year_id=academic_year_id,
                seed=candidate_seed,
                max_time_seconds=phase_budget,
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
            )
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
    else:
        futures = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            for idx in range(num_restarts):
                candidate_seed = base_seed + idx + 1
                init_mode = init_modes[idx % len(init_modes)]
                futures.append(
                    executor.submit(
                        _run_dry_candidate_solve,
                        run_id=run.id,
                        program_id=program_id,
                        academic_year_id=academic_year_id,
                        candidate_seed=candidate_seed,
                        candidate_budget=phase_budget,
                        enforce_teacher_load_limits=enforce_teacher_load_limits,
                        require_optimal=require_optimal,
                        hybrid_init_enabled=hybrid_init_enabled,
                        hybrid_population_size=hybrid_population_size,
                        hybrid_generations=hybrid_generations,
                        initialization_mode=init_mode,
                    )
                )

            for fut in as_completed(futures):
                candidate_seed, init_mode, candidate = fut.result()
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
        return _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=academic_year_id,
            seed=base_seed,
            max_time_seconds=max_time_seconds,
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
        )

    # Phase 2: adaptive LNS improvement rounds over the current best.
    lns_iterations = max(0, int(lns_iterations or 0))
    for lns_idx in range(lns_iterations):
        lns_budget = max(7.0, (max_time_seconds * 0.25) / max(1, lns_iterations))
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
        )
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
    final_result = _solve_program(
        db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        seed=best_seed,
        max_time_seconds=max_time_seconds,
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
    )

    telemetry_payload = {
        "multi_start_count": int(num_restarts),
        "lns_iterations_requested": int(lns_iterations),
        "strategy_scores": {k: float(v) for k, v in strategy_scores.items()},
        "lns_iterations": lns_telemetry_rows,
        "solution_pool": pool_summary,
        "selected_seed": int(best_seed),
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

    return final_result


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
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)

    # 1. Build context
    ctx = SolverContext(
        db=db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
        section_id_subset=section_id_subset,
        seed=seed,
        max_time_seconds=max_time_seconds,
        enforce_teacher_load_limits=enforce_teacher_load_limits,
        require_optimal=require_optimal,
        tenant_id=tenant_id,
    )
    if external_teacher_blocked_slot_ids:
        for teacher_id, slot_ids in external_teacher_blocked_slot_ids.items():
            if slot_ids:
                ctx.external_teacher_blocked_slot_ids[teacher_id].update(slot_ids)

    # 2. Load data
    load_all(ctx)

    # 3. Pre-solve locks (special allotments, fixed entries, teacher pruning)
    apply_pre_solve_locks(ctx)

    # 3b. OPTIMIZATION: build per-(section,subject) pruned slot lists.
    #     Must run AFTER apply_pre_solve_locks so teacher_disallowed_slot_ids
    #     is fully populated.  Variables step reads these lists directly.
    build_pruned_slots(ctx)

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
    create_variables(ctx)

    # 5. Add constraints
    add_constraints(ctx)

    # 6. Set objective
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

    # Adaptive solve budget: scale by model size while respecting caller cap.
    requested_cap = min(float(max_time_seconds), 300.0)
    initial_budget = _estimate_adaptive_budget_seconds(
        requested_cap=requested_cap,
        num_vars=num_vars,
        num_constraints=num_constraints,
        sections=len(ctx.sections),
        teachers=len(ctx.teachers),
        slots=len(ctx.slots),
        require_optimal=bool(require_optimal),
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = initial_budget
    solver.parameters.num_search_workers = os.cpu_count() or 8
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_presolve = True
    solver.parameters.symmetry_level = 2
    solver.parameters.randomize_search = True
    solver.parameters.search_branching = cp_model.AUTOMATIC_SEARCH
    solver.parameters.log_search_progress = True
    if seed is not None:
        solver.parameters.random_seed = int(seed)

    logger.info(
        "[solver] starting solve: requested_cap=%.0fs adaptive_budget=%.0fs workers=%d extended_solve=%s",
        requested_cap,
        initial_budget,
        solver.parameters.num_search_workers,
        allow_extended_solve,
    )
    status = solver.Solve(ctx.model)

    # Extended solve: if FEASIBLE (not proven optimal) and the caller opted in,
    # re-run with double the original budget (capped at 600 s) to try to close
    # the optimality gap.  The model is reused unchanged; CP-SAT resumes from
    # the incumbent solution it already has.
    if allow_extended_solve and status == cp_model.FEASIBLE:
        extended_cap = min(float(max_time_seconds) * 2, 600.0)
        already_spent = float(solver.WallTime() or 0.0)
        extra_budget = max(30.0, extended_cap - already_spent)
        logger.info(
            "[solver] status=FEASIBLE, launching focused improve pass: extra_budget=%.0fs (extended_cap=%.0fs)",
            extra_budget,
            extended_cap,
        )
        solver.parameters.max_time_in_seconds = extra_budget
        solver.parameters.randomize_search = True
        if seed is not None:
            solver.parameters.random_seed = int(seed) + 97
        status = solver.Solve(ctx.model)
        logger.info(
            "[solver] focused improve pass finished: status=%s wall_time=%.1fs",
            {0: "UNKNOWN", 2: "FEASIBLE", 3: "INFEASIBLE", 4: "OPTIMAL"}.get(int(status), str(status)),
            solver.WallTime(),
        )

    logger.info(
        "[solver] solve complete: status=%s wall_time=%.1fs",
        {0: "UNKNOWN", 2: "FEASIBLE", 3: "INFEASIBLE", 4: "OPTIMAL"}.get(int(status), str(status)),
        solver.WallTime(),
    )

    # 9. Handle infeasible / error
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _handle_infeasible(ctx, solver, status, persist_results=persist_results)

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

        hints_out = _extract_solution_hints(ctx, solver)
        lns_feedback = _build_lns_feedback(ctx, hints_out, solver)

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
) -> SolveResult:
    """Handle non-feasible solver outcomes."""
    ortools_status = int(status)
    diagnostics: list[dict] = []
    reason_summary: str | None = None
    tenant_id = ctx.tenant_id
    run = ctx.run

    if status == cp_model.INFEASIBLE:
        run.status = "INFEASIBLE"
        conflict_type = "INFEASIBLE"
        message = (
            "Solver infeasible due to special locked allotments."
            if ctx.special_allotments
            else "Solver could not find a feasible timetable."
        )

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
