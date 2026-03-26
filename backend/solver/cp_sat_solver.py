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

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.tenant import where_tenant
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
from solver.hybrid_initializer import generate_hybrid_hints
from solver.objective import add_objective
from solver.pre_solve_locks import apply_pre_solve_locks, check_teacher_window_feasibility
from solver.result_writer import write_results
from solver.variables import create_variables

logger = logging.getLogger(__name__)


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
) -> SolveResult:
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
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)

    q_years = (
        select(Section.academic_year_id)
        .where(Section.program_id == program_id)
        .where(Section.is_active.is_(True))
    )
    q_years = where_tenant(q_years, Section, tenant_id)
    year_ids = sorted({year_id for (year_id,) in db.execute(q_years).all() if year_id is not None})

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

    for idx, year_id in enumerate(year_ids):
        batches_left = max(1, len(year_ids) - idx)
        batch_budget = min(300.0, max(60.0, remaining_budget / batches_left))

        logger.info(
            "[solver] global decomposed batch=%d/%d year_id=%s budget=%.1fs blocked_teachers=%d",
            idx + 1,
            len(year_ids),
            str(year_id),
            batch_budget,
            len(teacher_schedule_map),
        )

        result = _solve_program(
            db,
            run=run,
            program_id=program_id,
            academic_year_id=year_id,
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
        remaining_budget = max(60.0, remaining_budget - elapsed)

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


def _solve_program(
    db: Session,
    *,
    run: TimetableRun,
    program_id,
    academic_year_id,
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
) -> SolveResult:
    tenant_id = getattr(run, "tenant_id", None)

    # 1. Build context
    ctx = SolverContext(
        db=db,
        run=run,
        program_id=program_id,
        academic_year_id=academic_year_id,
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
            hints = generate_hybrid_hints(
                ctx,
                seed=seed,
                population_size=int(hybrid_population_size),
                generations=int(hybrid_generations),
            )
            for var, val in hints.items():
                ctx.model.AddHint(var, int(val))
            logger.info("[solver] hybrid hints applied: %d", len(hints))
        except Exception:
            logger.warning("[solver] hybrid initialization failed; continuing without hints", exc_info=True)

    # 7. Search strategy hints — guide CP-SAT to branch on the most
    #    constrained decision variables first (section-slot assignments).
    _add_search_hints(ctx)

    # 8. Solve
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

    # Enforce a hard 5-minute (300 s) cap on the initial solve budget.
    # Callers may request less time; they cannot request more than 300 s here.
    initial_budget = min(float(max_time_seconds), 300.0)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = initial_budget
    solver.parameters.num_search_workers = os.cpu_count() or 8
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_presolve = True
    solver.parameters.symmetry_level = 2
    solver.parameters.log_search_progress = True
    if seed is not None:
        solver.parameters.random_seed = int(seed)

    logger.info(
        "[solver] starting solve: budget=%.0fs workers=%d extended_solve=%s",
        initial_budget, solver.parameters.num_search_workers, allow_extended_solve,
    )
    status = solver.Solve(ctx.model)

    # Extended solve: if FEASIBLE (not proven optimal) and the caller opted in,
    # re-run with double the original budget (capped at 600 s) to try to close
    # the optimality gap.  The model is reused unchanged; CP-SAT resumes from
    # the incumbent solution it already has.
    if allow_extended_solve and status == cp_model.FEASIBLE:
        extended_budget = min(float(max_time_seconds) * 2, 600.0)
        logger.info(
            "[solver] status=FEASIBLE, launching extended solve: budget=%.0fs",
            extended_budget,
        )
        solver.parameters.max_time_in_seconds = extended_budget
        status = solver.Solve(ctx.model)
        logger.info(
            "[solver] extended solve finished: status=%s wall_time=%.1fs",
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
        return _handle_infeasible(ctx, solver, status)

    # 10. Write results
    return write_results(ctx, solver, status, clear_existing_entries=clear_existing_entries)


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
    ctx.db.add(conflict)
    ctx.db.commit()
    return SolveResult(
        status=str(run.status),
        entries_written=0,
        conflicts=[conflict],
        diagnostics=diagnostics,
        reason_summary=reason_summary,
    )
