"""Solver analytics engine — track metrics, penalties, and constraints during solve.

Collects comprehensive analytics data during CP-SAT solving to enable:
- Penalty breakdown (which constraints are most expensive)
- Constraint violation tracking
- Performance diagnostics
- Solution quality assessment
- Debugging and transparency

All data stored in SolverContext for retrieval after solve.
No external dependencies (no Redis, no background jobs).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PenaltyBreakdown:
    """Tracks each soft constraint's contribution to total penalty."""
    
    # Constraint penalties (accumulated during solve)
    section_gap_penalty: int = 0
    teacher_gap_penalty: int = 0
    subject_spread_penalty: int = 0
    daily_balance_penalty: int = 0
    teacher_weekly_overload_penalty: int = 0
    teacher_daily_overload_penalty: int = 0
    teacher_continuity_penalty: int = 0
    teacher_preferred_slot_penalty: int = 0
    slot_balance_penalty: int = 0
    slot_overload_penalty: int = 0
    late_slot_penalty: int = 0
    friday_last_penalty: int = 0
    session_under_penalty: int = 0
    session_over_penalty: int = 0
    room_compatibility_penalty: int = 0
    elective_sync_penalty: int = 0
    lab_day_gap_penalty: int = 0
    theory_room_overflow_penalty: int = 0
    lab_room_overflow_penalty: int = 0
    slot_capacity_overflow_penalty: int = 0
    
    # Custom weights used
    weights: dict[str, int] = field(default_factory=dict)
    
    def total(self) -> int:
        """Sum all penalties."""
        return (
            self.section_gap_penalty +
            self.teacher_gap_penalty +
            self.subject_spread_penalty +
            self.daily_balance_penalty +
            self.teacher_weekly_overload_penalty +
            self.teacher_daily_overload_penalty +
            self.teacher_continuity_penalty +
            self.teacher_preferred_slot_penalty +
            self.slot_balance_penalty +
            self.slot_overload_penalty +
            self.late_slot_penalty +
            self.friday_last_penalty +
            self.session_under_penalty +
            self.session_over_penalty +
            self.room_compatibility_penalty +
            self.elective_sync_penalty +
            self.lab_day_gap_penalty +
            self.theory_room_overflow_penalty +
            self.lab_room_overflow_penalty +
            self.slot_capacity_overflow_penalty
        )
    
    def as_dict(self) -> dict[str, int]:
        """Return as sortable dictionary."""
        return {
            "section_gaps": self.section_gap_penalty,
            "teacher_gaps": self.teacher_gap_penalty,
            "subject_spread": self.subject_spread_penalty,
            "daily_balance": self.daily_balance_penalty,
            "teacher_weekly_overload": self.teacher_weekly_overload_penalty,
            "teacher_daily_overload": self.teacher_daily_overload_penalty,
            "teacher_continuity": self.teacher_continuity_penalty,
            "teacher_preferred_slots": self.teacher_preferred_slot_penalty,
            "slot_balance": self.slot_balance_penalty,
            "slot_overload": self.slot_overload_penalty,
            "late_slots": self.late_slot_penalty,
            "friday_last": self.friday_last_penalty,
            "session_under": self.session_under_penalty,
            "session_over": self.session_over_penalty,
            "room_compatibility": self.room_compatibility_penalty,
            "elective_sync": self.elective_sync_penalty,
            "lab_day_gaps": self.lab_day_gap_penalty,
            "theory_room_overflow": self.theory_room_overflow_penalty,
            "lab_room_overflow": self.lab_room_overflow_penalty,
            "slot_capacity_overflow": self.slot_capacity_overflow_penalty,
        }
    
    def top_contributors(self, n: int = 5) -> list[tuple[str, int]]:
        """Return top N penalty contributors."""
        sorted_items = sorted(self.as_dict().items(), key=lambda x: x[1], reverse=True)
        return sorted_items[:n]


@dataclass
class ConstraintViolationSummary:
    """Tracks violations of each constraint across all entries."""
    
    teacher_overload_count: int = 0          # Teachers exceeding daily/weekly limit
    room_overflow_slot_count: int = 0         # Slots exceeding room capacity
    slot_congestion_count: int = 0            # Slots with excessive load
    gap_instances: int = 0                    # Number of gaps in schedules
    section_imbalance_count: int = 0          # Sections with uneven daily load
    teacher_imbalance_count: int = 0          # Teachers with uneven daily load
    elective_mismatch_count: int = 0          # Elective subjects not synchronized
    lab_day_gap_count: int = 0                # Labs with non-contiguous days
    room_type_mismatch_count: int = 0         # Wrong room type for subject
    
    def total_violations(self) -> int:
        """Total count of all violations."""
        return (
            self.teacher_overload_count +
            self.room_overflow_slot_count +
            self.slot_congestion_count +
            self.gap_instances +
            self.section_imbalance_count +
            self.teacher_imbalance_count +
            self.elective_mismatch_count +
            self.lab_day_gap_count +
            self.room_type_mismatch_count
        )
    
    def as_dict(self) -> dict[str, int]:
        """Return as dictionary."""
        return {
            "teacher_overload": self.teacher_overload_count,
            "room_overflow_slots": self.room_overflow_slot_count,
            "slot_congestion": self.slot_congestion_count,
            "gaps": self.gap_instances,
            "section_imbalance": self.section_imbalance_count,
            "teacher_imbalance": self.teacher_imbalance_count,
            "elective_mismatch": self.elective_mismatch_count,
            "lab_day_gaps": self.lab_day_gap_count,
            "room_type_mismatch": self.room_type_mismatch_count,
        }


@dataclass
class SolverPhaseMetrics:
    """Track metrics for each phase of solving."""
    
    load_time_seconds: float = 0.0
    domain_reduction_time_seconds: float = 0.0
    presolve_locks_time_seconds: float = 0.0
    variable_creation_time_seconds: float = 0.0
    constraint_addition_time_seconds: float = 0.0
    objective_setup_time_seconds: float = 0.0
    cp_sat_presolve_time_seconds: float = 0.0
    cp_sat_search_time_seconds: float = 0.0
    result_writing_time_seconds: float = 0.0
    total_solve_time_seconds: float = 0.0
    
    def as_dict(self) -> dict[str, float]:
        """Return as dictionary."""
        return {
            "load": self.load_time_seconds,
            "domain_reduction": self.domain_reduction_time_seconds,
            "presolve_locks": self.presolve_locks_time_seconds,
            "variable_creation": self.variable_creation_time_seconds,
            "constraint_addition": self.constraint_addition_time_seconds,
            "objective_setup": self.objective_setup_time_seconds,
            "cp_sat_presolve": self.cp_sat_presolve_time_seconds,
            "cp_sat_search": self.cp_sat_search_time_seconds,
            "result_writing": self.result_writing_time_seconds,
            "total": self.total_solve_time_seconds,
        }


@dataclass
class SolverAnalytics:
    """Complete analytics snapshot for a single solve."""
    
    # Solve metadata
    problem_size: dict[str, int] = field(default_factory=dict)  # sections, subjects, teachers, etc.
    variables_created: int = 0
    constraints_created: int = 0
    cp_sat_solver_status: str = ""
    cp_sat_solve_time_seconds: float = 0.0
    total_objective_value: int = 0
    best_objective_bound: int | None = None
    optimality_gap: int | None = None
    
    # Penalties
    penalty_breakdown: PenaltyBreakdown = field(default_factory=PenaltyBreakdown)
    
    # Violations
    violations: ConstraintViolationSummary = field(default_factory=ConstraintViolationSummary)
    
    # Timing
    phase_metrics: SolverPhaseMetrics = field(default_factory=SolverPhaseMetrics)
    
    # Solution quality
    entries_written: int = 0
    coverage_percentage: float = 0.0  # % of required sessions fulfilled
    teacher_average_load: float = 0.0
    section_average_load: float = 0.0
    room_utilization_percentage: float = 0.0
    
    # Fallback info
    greedy_fallback_invoked: bool = False
    greedy_fallback_reason: str = ""
    greedy_fallback_entries_count: int = 0
    
    # Domain reduction stats
    domain_reduction_stats: dict[str, Any] = field(default_factory=dict)
    
    def as_dict(self) -> dict[str, Any]:
        """Export complete analytics as dictionary."""
        return {
            "problem_size": self.problem_size,
            "variables_created": self.variables_created,
            "constraints_created": self.constraints_created,
            "cp_sat_status": self.cp_sat_solver_status,
            "cp_sat_solve_time_seconds": self.cp_sat_solve_time_seconds,
            "total_objective_value": self.total_objective_value,
            "best_objective_bound": self.best_objective_bound,
            "optimality_gap": self.optimality_gap,
            "penalty_breakdown": self.penalty_breakdown.as_dict(),
            "penalty_total": self.penalty_breakdown.total(),
            "violations": self.violations.as_dict(),
            "violations_total": self.violations.total_violations(),
            "phase_metrics": self.phase_metrics.as_dict(),
            "entries_written": self.entries_written,
            "coverage_percentage": self.coverage_percentage,
            "teacher_average_load": self.teacher_average_load,
            "section_average_load": self.section_average_load,
            "room_utilization_percentage": self.room_utilization_percentage,
            "greedy_fallback_invoked": self.greedy_fallback_invoked,
            "greedy_fallback_reason": self.greedy_fallback_reason,
            "greedy_fallback_entries_count": self.greedy_fallback_entries_count,
            "domain_reduction_stats": self.domain_reduction_stats,
        }


def initialize_analytics(ctx) -> None:
    """Initialize analytics in SolverContext."""
    if not hasattr(ctx, 'analytics'):
        ctx.analytics = SolverAnalytics()
    logger.info("Analytics initialized for solve session")


def calculate_penalty_breakdown(ctx) -> PenaltyBreakdown:
    """Calculate penalty contribution from each soft constraint term.
    
    Call after CP-SAT solver completes to extract penalty values.
    """
    breakdown = PenaltyBreakdown()
    
    if not hasattr(ctx, 'model'):
        return breakdown
    
    solver = ctx.model.Proto()
    
    # For each objective term, calculate its contribution
    # This is a high-level estimation based on weights
    # In practice, extract from CP-SAT solver statistics if available
    
    # Section gap penalties (w=500)
    if hasattr(ctx, 'internal_gap_terms'):
        breakdown.section_gap_penalty = len(ctx.internal_gap_terms) * 500
    
    # Teacher gap penalties (w=300)
    if hasattr(ctx, 'teacher_gap_terms'):
        breakdown.teacher_gap_penalty = len(ctx.teacher_gap_terms) * 300
    
    # Teacher overload (w=700, w=520)
    if hasattr(ctx, 'teacher_weekly_overload_terms'):
        breakdown.teacher_weekly_overload_penalty = len(ctx.teacher_weekly_overload_terms) * 700
    if hasattr(ctx, 'teacher_daily_overload_terms'):
        breakdown.teacher_daily_overload_penalty = len(ctx.teacher_daily_overload_terms) * 520
    
    # Room overflow (w=200)
    if hasattr(ctx, 'theory_room_overflow_terms'):
        breakdown.theory_room_overflow_penalty = len(ctx.theory_room_overflow_terms) * 200
    if hasattr(ctx, 'lab_room_overflow_terms'):
        breakdown.lab_room_overflow_penalty = len(ctx.lab_room_overflow_terms) * 200
    
    # Subject spread (w=400)
    if hasattr(ctx, 'subject_spread_penalty_terms'):
        breakdown.subject_spread_penalty = len(ctx.subject_spread_penalty_terms) * 400
    
    return breakdown


def analyze_constraint_violations(ctx, entries: list) -> ConstraintViolationSummary:
    """Analyze completed timetable for constraint violations.
    
    Called after solve to count how many violations occurred.
    """
    from collections import defaultdict
    
    violations = ConstraintViolationSummary()
    
    if not entries:
        return violations
    
    # Build slot_by_id mapping
    slot_by_id = {slot.id: slot for slot in ctx.slots}
    
    # Track loads per teacher and section
    teacher_daily_load = defaultdict(lambda: defaultdict(int))
    section_daily_load = defaultdict(lambda: defaultdict(int))
    slot_load = defaultdict(int)
    room_daily_load = defaultdict(lambda: defaultdict(int))
    
    for entry in entries:
        slot = slot_by_id.get(entry.slot_id)
        if not slot:
            continue
        
        teacher_daily_load[entry.teacher_id][slot.day_of_week] += 1
        section_daily_load[entry.section_id][slot.day_of_week] += 1
        slot_load[entry.slot_id] += 1
        room_daily_load[entry.room_id][slot.day_of_week] += 1
    
    # Check teacher overload (if daily > some limit, e.g., 5)
    for teacher_id, daily in teacher_daily_load.items():
        for day, load in daily.items():
            if load > 5:  # Heuristic daily limit
                violations.teacher_overload_count += 1
    
    # Check room overflow (if slot > available rooms)
    theory_rooms = len(ctx.rooms_by_type.get("CLASSROOM", []))
    for slot_id, load in slot_load.items():
        if load > theory_rooms + 5:  # Heuristic with buffer
            violations.room_overflow_slot_count += 1
    
    # Check slot congestion (if > 30 classes in slot)
    violations.slot_congestion_count = sum(1 for load in slot_load.values() if load > 30)
    
    return violations


def generate_solution_quality_metrics(ctx, entries: list) -> dict[str, float]:
    """Calculate solution quality metrics."""
    from collections import defaultdict
    
    if not entries:
        return {
            "coverage_percentage": 0.0,
            "teacher_average_load": 0.0,
            "section_average_load": 0.0,
            "room_utilization_percentage": 0.0,
        }
    
    # Coverage: how many required sessions were assigned
    assigned_sessions = len(entries)
    total_required_sessions = sum(
        ctx.subject_required_sessions.get((sec_id, subj_id), 0)
        for (sec_id, subj_id) in ctx.valid_slots_by_section_subject.keys()
    )
    coverage = (assigned_sessions / total_required_sessions * 100) if total_required_sessions > 0 else 0.0
    
    # Teacher average load
    teacher_sessions = defaultdict(int)
    for entry in entries:
        teacher_sessions[entry.teacher_id] += 1
    teacher_avg = sum(teacher_sessions.values()) / len(teacher_sessions) if teacher_sessions else 0.0
    
    # Section average load
    section_sessions = defaultdict(int)
    for entry in entries:
        section_sessions[entry.section_id] += 1
    section_avg = sum(section_sessions.values()) / len(section_sessions) if section_sessions else 0.0
    
    # Room utilization
    total_rooms = len(ctx.rooms_all)
    room_sessions = defaultdict(int)
    for entry in entries:
        room_sessions[entry.room_id] += 1
    rooms_used = len([r for r in room_sessions.values() if r > 0])
    utilization = (rooms_used / total_rooms * 100) if total_rooms > 0 else 0.0
    
    return {
        "coverage_percentage": coverage,
        "teacher_average_load": teacher_avg,
        "section_average_load": section_avg,
        "room_utilization_percentage": utilization,
    }


def finalize_analytics(ctx, result) -> SolverAnalytics:
    """Finalize analytics with result data."""
    
    analytics = ctx.analytics if hasattr(ctx, 'analytics') else SolverAnalytics()
    
    # Update problem size
    analytics.problem_size = {
        "sections": len(ctx.sections),
        "subjects": len(ctx.subjects),
        "teachers": len(ctx.teachers),
        "rooms": len(ctx.rooms_all),
        "time_slots": len(ctx.slots),
    }
    
    # Update solve info
    analytics.cp_sat_solver_status = result.status
    analytics.cp_sat_solve_time_seconds = result.solve_time_seconds or 0.0
    analytics.total_objective_value = result.objective_score or 0
    analytics.best_objective_bound = result.best_objective_bound
    analytics.optimality_gap = result.optimality_gap
    
    # Penalty breakdown
    analytics.penalty_breakdown = calculate_penalty_breakdown(ctx)
    
    # Solution quality
    analytics.entries_written = result.entries_written
    
    quality_metrics = generate_solution_quality_metrics(ctx, result.conflicts)  # Use available data
    analytics.coverage_percentage = quality_metrics.get("coverage_percentage", 0.0)
    analytics.teacher_average_load = quality_metrics.get("teacher_average_load", 0.0)
    analytics.section_average_load = quality_metrics.get("section_average_load", 0.0)
    analytics.room_utilization_percentage = quality_metrics.get("room_utilization_percentage", 0.0)
    
    # Fallback info
    if "GREEDY_FALLBACK" in (result.warnings or []):
        analytics.greedy_fallback_invoked = True
        analytics.greedy_fallback_reason = "CP-SAT returned INFEASIBLE or UNKNOWN"
        analytics.greedy_fallback_entries_count = result.entries_written
    
    logger.info(f"Analytics finalized: {analytics.entries_written} entries, objective={analytics.total_objective_value}")
    
    return analytics
