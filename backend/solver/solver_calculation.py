"""Pre-solve calculation module — analyze problem characteristics before solving.

Performs rapid pre-solve analysis to:
- Detect potential overload situations
- Estimate room demand
- Calculate slot pressure maps
- Assess feasibility of constraints
- Guide solver parameter tuning

All computations complete in <1 second (no solving).
Results stored in SolverContext for use during solve and reporting.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TeacherLoadAnalysis:
    """Teacher capacity analysis."""
    
    teacher_id: str
    teacher_name: str
    required_load: int                    # Total sessions to teach
    preferred_weekly_limit: int           # Preferred max per week
    overload_expected: bool               # Will exceed limit?
    overload_percentage: float            # How much over limit?
    daily_peaks: list[int] = field(default_factory=list)  # Max daily load across week


@dataclass
class RoomDemandAnalysis:
    """Room capacity analysis."""
    
    room_type: str                        # "CLASSROOM", "LAB", etc.
    theory_rooms_available: int           # Count of available CLASSROOM/LT
    lab_rooms_available: int              # Count of available LAB
    peak_parallel_demand: int             # Max simultaneous classes
    overflow_expected: bool               # Peak > available?
    overflow_percentage: float            # By how much?
    peak_slots: list[str] = field(default_factory=list)  # When peak occurs


@dataclass
class SlotPressureMap:
    """Slot-by-slot load analysis."""
    
    slot_id: str
    day_of_week: int
    period: int
    parallel_classes: int                 # How many classes in parallel
    demand_percentage: float              # % of room capacity required
    congestion_level: str                 # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    capacity_slack: int                   # Rooms available after assignment


@dataclass
class SectionLoadAnalysis:
    """Section (student group) capacity analysis."""
    
    section_id: str
    section_code: str
    total_required_hours: int             # Total hours of instruction
    max_hours_per_day: int                # Preferred max per day
    imbalance_expected: bool              # Uneven daily distribution likely?
    estimated_daily_load: list[int] = field(default_factory=list)


@dataclass
class ConstraintFeasibilityCheck:
    """Assessment of constraint feasibility."""
    
    feasible: bool                        # Is this feasible to schedule?
    warning_level: str                    # "NONE", "WARNING", "CRITICAL"
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PreSolveCalculations:
    """Complete pre-solve analysis snapshot."""
    
    # Analyses
    teacher_loads: list[TeacherLoadAnalysis] = field(default_factory=list)
    room_demand: RoomDemandAnalysis | None = None
    slot_pressures: list[SlotPressureMap] = field(default_factory=list)
    section_loads: list[SectionLoadAnalysis] = field(default_factory=list)
    feasibility_check: ConstraintFeasibilityCheck | None = None
    
    # Summary statistics
    overloaded_teachers_count: int = 0
    slots_at_capacity: int = 0
    slots_over_capacity: int = 0
    sections_imbalanced: int = 0
    
    # Recommendations
    solver_recommendations: list[str] = field(default_factory=list)
    data_quality_warnings: list[str] = field(default_factory=list)
    
    computation_time_seconds: float = 0.0
    
    def as_dict(self) -> dict[str, Any]:
        """Export as dictionary."""
        return {
            "teacher_loads": [
                {
                    "teacher_id": t.teacher_id,
                    "teacher_name": t.teacher_name,
                    "required_load": t.required_load,
                    "preferred_limit": t.preferred_weekly_limit,
                    "overload_expected": t.overload_expected,
                    "overload_percentage": t.overload_percentage,
                }
                for t in self.teacher_loads
            ],
            "room_demand": {
                "theory_rooms_available": self.room_demand.theory_rooms_available,
                "lab_rooms_available": self.room_demand.lab_rooms_available,
                "peak_parallel_demand": self.room_demand.peak_parallel_demand,
                "overflow_expected": self.room_demand.overflow_expected,
                "overflow_percentage": self.room_demand.overflow_percentage,
            } if self.room_demand else None,
            "slots_at_capacity": self.slots_at_capacity,
            "slots_over_capacity": self.slots_over_capacity,
            "overloaded_teachers": self.overloaded_teachers_count,
            "sections_imbalanced": self.sections_imbalanced,
            "warnings": self.data_quality_warnings,
            "recommendations": self.solver_recommendations,
            "feasibility": {
                "feasible": self.feasibility_check.feasible if self.feasibility_check else True,
                "warning_level": self.feasibility_check.warning_level if self.feasibility_check else "NONE",
                "issues": self.feasibility_check.issues if self.feasibility_check else [],
            },
        }


def analyze_teacher_loads(ctx) -> list[TeacherLoadAnalysis]:
    """Analyze each teacher's session load."""
    analyses = []
    
    for teacher in ctx.teachers:
        # Calculate required load for this teacher
        # Iterate over all (section, subject) pairs in the problem
        required_sessions = 0
        for (sec_id, subj_id) in ctx.valid_slots_by_section_subject.keys():
            # Count sessions assigned to this teacher for this (section, subject)
            assigned_teacher = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
            if assigned_teacher == teacher.id:
                required_count = ctx.subject_required_sessions.get((sec_id, subj_id), 0)
                required_sessions += required_count
        
        preferred_limit = getattr(teacher, "preferred_weekly_load", 30)
        
        overload_expected = required_sessions > preferred_limit
        overload_pct = (
            ((required_sessions - preferred_limit) / preferred_limit * 100)
            if preferred_limit > 0
            else 0
        )
        
        daily_peaks = [required_sessions // 5] * 5  # Rough estimate
        
        analysis = TeacherLoadAnalysis(
            teacher_id=str(teacher.id),
            teacher_name=teacher.full_name,
            required_load=required_sessions,
            preferred_weekly_limit=preferred_limit,
            overload_expected=overload_expected,
            overload_percentage=max(0, overload_pct),
            daily_peaks=daily_peaks,
        )
        analyses.append(analysis)
    
    return analyses


def analyze_room_demand(ctx) -> RoomDemandAnalysis:
    """Analyze peak room demand vs availability."""
    
    # Count available rooms by type
    theory_rooms = len(ctx.rooms_by_type.get("CLASSROOM", [])) + len(ctx.rooms_by_type.get("LT", []))
    lab_rooms = len(ctx.rooms_by_type.get("LAB", []))
    
    # Estimate peak parallel demand
    # Peak demand ≈ (total sessions / 40 slots) on peak day
    total_sessions = sum(
        ctx.subject_required_sessions.get((sec_id, subj_id), 0)
        for (sec_id, subj_id) in ctx.valid_slots_by_section_subject.keys()
    )
    peak_parallel = max(1, total_sessions // 30)  # Rough heuristic
    
    overflow_expected = peak_parallel > (theory_rooms + lab_rooms)
    overflow_pct = (
        ((peak_parallel - (theory_rooms + lab_rooms)) / (theory_rooms + lab_rooms) * 100)
        if (theory_rooms + lab_rooms) > 0
        else 0
    )
    
    analysis = RoomDemandAnalysis(
        room_type="ALL",
        theory_rooms_available=theory_rooms,
        lab_rooms_available=lab_rooms,
        peak_parallel_demand=peak_parallel,
        overflow_expected=overflow_expected,
        overflow_percentage=max(0, overflow_pct),
        peak_slots=[],
    )
    
    return analysis


def calculate_slot_pressure_map(ctx) -> list[SlotPressureMap]:
    """Calculate expected slot pressure from required sessions and pruned domains."""
    pressures = []

    if not ctx.slots:
        return pressures

    demand_by_slot: dict[Any, float] = defaultdict(float)

    for sec_id, subject_list in ctx.section_required.items():
        section = ctx.section_by_id.get(sec_id)
        track = str(getattr(section, "track", "CORE") or "CORE") if section is not None else "CORE"

        for subj_id, sessions_override in subject_list:
            subj = ctx.subject_by_id.get(subj_id)
            if subj is None:
                continue

            sessions_required = (
                int(sessions_override)
                if sessions_override is not None
                else int(ctx.subject_required_sessions.get((sec_id, subj_id), 0) or 0)
            )
            if sessions_required <= 0:
                sessions_required = int(getattr(subj, "sessions_per_week", 0) or 0)
            if sessions_required <= 0:
                continue

            valid_slots = list(ctx.valid_slots_by_section_subject.get((sec_id, subj_id), []) or [])
            if not valid_slots:
                valid_slots = list(sorted(ctx.allowed_slots_by_section.get(sec_id, set()) or []))
            if not valid_slots:
                continue

            is_lab = str(getattr(subj, "subject_type", "THEORY")) == "LAB"
            if not is_lab:
                per_slot = float(sessions_required) / float(len(valid_slots))
                for slot_id in valid_slots:
                    demand_by_slot[slot_id] += per_slot
                continue

            block = int(ctx.duration_for(subj_id, track=track) or getattr(subj, "lab_block_size_slots", 1) or 1)
            if block < 1:
                block = 1

            covered_count_by_slot: dict[Any, int] = defaultdict(int)
            total_covered_positions = 0
            for start_slot_id in valid_slots:
                di = ctx.slot_info.get(start_slot_id)
                if not di:
                    covered_count_by_slot[start_slot_id] += 1
                    total_covered_positions += 1
                    continue

                day, start_idx = int(di[0]), int(di[1])
                covered_here = 0
                for j in range(block):
                    ts = ctx.slot_by_day_index.get((day, start_idx + j))
                    if ts is None:
                        continue
                    covered_count_by_slot[ts.id] += 1
                    covered_here += 1
                total_covered_positions += max(1, covered_here)

            if total_covered_positions <= 0:
                continue

            total_required_slot_load = float(sessions_required * block)
            for slot_id, count in covered_count_by_slot.items():
                demand_by_slot[slot_id] += total_required_slot_load * (float(count) / float(total_covered_positions))

    available_rooms = int(
        sum(
            1
            for r in ctx.rooms_all
            if bool(getattr(r, "is_active", True)) and not bool(getattr(r, "is_special", False))
        )
    )

    ordered_slots = sorted(
        ctx.slots,
        key=lambda s: (int(getattr(s, "day_of_week", 0) or 0), int(getattr(s, "slot_index", 0) or 0)),
    )
    for slot in ordered_slots:
        expected_parallel = float(demand_by_slot.get(slot.id, 0.0) or 0.0)
        parallel_load = max(0, int(round(expected_parallel)))

        if available_rooms > 0:
            demand_pct = (float(expected_parallel) / float(available_rooms)) * 100.0
            capacity_slack = max(0, int(available_rooms - parallel_load))
        else:
            demand_pct = 100.0 if expected_parallel > 0 else 0.0
            capacity_slack = 0

        if demand_pct > 100:
            congestion = "CRITICAL"
        elif demand_pct > 80:
            congestion = "HIGH"
        elif demand_pct > 50:
            congestion = "MEDIUM"
        else:
            congestion = "LOW"

        pressures.append(
            SlotPressureMap(
                slot_id=str(slot.id),
                day_of_week=int(getattr(slot, "day_of_week", 0) or 0),
                period=int(getattr(slot, "slot_index", 0) or 0),
                parallel_classes=parallel_load,
                demand_percentage=float(demand_pct),
                congestion_level=congestion,
                capacity_slack=capacity_slack,
            )
        )

    return pressures


def analyze_section_loads(ctx) -> list[SectionLoadAnalysis]:
    """Analyze each section's daily load distribution."""
    analyses = []
    
    for section in ctx.sections:
        # Calculate total required hours for this section
        total_hours = sum(
            ctx.subject_required_sessions.get((section.id, subj_id), 0)
            for subj_id in [s.id for s in ctx.subjects]
        )
        
        max_hours_per_day = 6  # Heuristic
        imbalance_expected = total_hours > (max_hours_per_day * 5)  # More than 1 day can handle
        
        daily_load = [total_hours // 5] * 5  # Rough estimate
        
        analysis = SectionLoadAnalysis(
            section_id=str(section.id),
            section_code=section.code,
            total_required_hours=total_hours,
            max_hours_per_day=max_hours_per_day,
            imbalance_expected=imbalance_expected,
            estimated_daily_load=daily_load,
        )
        analyses.append(analysis)
    
    return analyses


def check_constraint_feasibility(ctx) -> ConstraintFeasibilityCheck:
    """Quick feasibility check."""
    issues = []
    recommendations = []
    warning_level = "NONE"
    
    # Check 1: Room availability
    total_rooms = len(ctx.rooms_all)
    if total_rooms < 5:
        issues.append(f"CRITICAL: Only {total_rooms} rooms available (need ≥10)")
        warning_level = "CRITICAL"
        recommendations.append("Add more rooms to system")
    
    # Check 2: Teacher availability
    fully_booked_teachers = sum(
        1 for t in ctx.teachers
        if len(ctx.valid_slots_by_section_subject.get((t.id,), set())) < 5
    )
    if fully_booked_teachers > 0:
        issues.append(f"WARNING: {fully_booked_teachers} teachers have very few free slots")
        if warning_level == "NONE":
            warning_level = "WARNING"
        recommendations.append("Review teacher availability windows")
    
    # Check 3: Time slots
    if len(ctx.slots) < 30:
        issues.append(f"WARNING: Only {len(ctx.slots)} slots defined (typically ≥40)")
        if warning_level == "NONE":
            warning_level = "WARNING"
    
    # Check 4: Sections vs capacity
    section_load_sum = sum(
        sum(
            ctx.subject_required_sessions.get((sec.id, subj.id), 0)
            for subj in ctx.subjects
        )
        for sec in ctx.sections
    )
    
    max_slot_capacity = len(ctx.rooms_all) * len(ctx.slots)
    if section_load_sum > max_slot_capacity:
        issues.append(f"CRITICAL: Total session demand ({section_load_sum}) exceeds slot capacity ({max_slot_capacity})")
        warning_level = "CRITICAL"
        recommendations.append("Reduce section load or add more time slots/rooms")
    
    feasible = warning_level != "CRITICAL"
    
    return ConstraintFeasibilityCheck(
        feasible=feasible,
        warning_level=warning_level,
        issues=issues,
        recommendations=recommendations,
    )


def generate_solver_recommendations(calc: PreSolveCalculations) -> list[str]:
    """Generate recommendations for solver tuning based on problem characteristics."""
    recommendations = []
    
    # Based on room demand
    if calc.room_demand and calc.room_demand.overflow_expected:
        recommendations.append("Set room_balance_mode='soft' to allow overflow with penalties")
    
    # Based on teacher overload
    if calc.overloaded_teachers_count > 5:
        recommendations.append("Consider increasing teacher preferred_weekly_load limits")
    
    # Based on slot congestion
    if calc.slots_over_capacity > 10:
        recommendations.append("Add more time slots or reduce section loads")
    
    # Based on feasibility
    if calc.feasibility_check:
        if not calc.feasibility_check.feasible:
            recommendations.extend(calc.feasibility_check.recommendations)
    
    return recommendations


def calculate_pre_solve_statistics(ctx) -> PreSolveCalculations:
    """Execute complete pre-solve analysis."""
    import time
    start = time.time()
    
    logger.info("=== PRE-SOLVE CALCULATIONS STARTING ===")
    
    # Build subject_required_sessions dict from section_required for convenience
    # Format: {(section_id, subject_id): session_count}
    subject_required_sessions = {}
    for section_id, subject_list in ctx.section_required.items():
        for subject_id, session_count in subject_list:
            if session_count is not None:
                subject_required_sessions[(section_id, subject_id)] = int(session_count)
                continue
            subj = ctx.subject_by_id.get(subject_id)
            fallback = int(getattr(subj, "sessions_per_week", 0) or 0) if subj is not None else 0
            if fallback > 0:
                subject_required_sessions[(section_id, subject_id)] = fallback
    
    # Inject into context for use by analysis functions
    ctx.subject_required_sessions = subject_required_sessions
    
    # 1. Analyze teachers
    teacher_loads = analyze_teacher_loads(ctx)
    overloaded_count = sum(1 for t in teacher_loads if t.overload_expected)
    logger.info(f"Teacher analysis: {len(teacher_loads)} teachers, {overloaded_count} overloaded")
    
    # 2. Analyze room demand
    room_demand = analyze_room_demand(ctx)
    logger.info(f"Room demand: peak {room_demand.peak_parallel_demand}, available {room_demand.theory_rooms_available + room_demand.lab_rooms_available}")
    
    # 3. Calculate slot pressures
    slot_pressures = calculate_slot_pressure_map(ctx)
    slots_critical = sum(1 for s in slot_pressures if s.congestion_level == "CRITICAL")
    logger.info(f"Slot analysis: {len(slot_pressures)} slots, {slots_critical} CRITICAL")
    
    # 4. Analyze sections
    section_loads = analyze_section_loads(ctx)
    sections_imbalanced = sum(1 for s in section_loads if s.imbalance_expected)
    logger.info(f"Section analysis: {len(section_loads)} sections, {sections_imbalanced} imbalanced")
    
    # 5. Feasibility check
    feasibility = check_constraint_feasibility(ctx)
    logger.info(f"Feasibility check: {feasibility.warning_level}, feasible={feasibility.feasible}")
    
    # 6. Create calculations object
    calc = PreSolveCalculations(
        teacher_loads=teacher_loads,
        room_demand=room_demand,
        slot_pressures=slot_pressures,
        section_loads=section_loads,
        feasibility_check=feasibility,
        overloaded_teachers_count=overloaded_count,
        slots_at_capacity=sum(1 for s in slot_pressures if s.congestion_level in ("HIGH", "MEDIUM")),
        slots_over_capacity=sum(1 for s in slot_pressures if s.congestion_level == "CRITICAL"),
        sections_imbalanced=sections_imbalanced,
    )
    
    # 7. Generate recommendations
    calc.solver_recommendations = generate_solver_recommendations(calc)
    calc.data_quality_warnings = feasibility.issues
    
    calc.computation_time_seconds = time.time() - start
    
    logger.info(f"=== PRE-SOLVE CALCULATIONS COMPLETE ({calc.computation_time_seconds:.2f}s) ===")
    
    return calc


def initialize_calculations(ctx) -> None:
    """Initialize and store pre-solve calculations in context."""
    ctx.pre_solve_calculations = calculate_pre_solve_statistics(ctx)
