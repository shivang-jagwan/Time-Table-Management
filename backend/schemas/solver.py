from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateTimetableRequest(BaseModel):
    program_code: str = Field(min_length=1)
    academic_year_number: int = Field(ge=1, le=4)
    seed: int | None = None


class GenerateGlobalTimetableRequest(BaseModel):
    """Program-wide request.

    Schedules all active sections of the program across all years.
    """

    program_code: str = Field(min_length=1)
    seed: int | None = None


class SolveTimetableRequest(GenerateTimetableRequest):
    max_time_seconds: float = Field(default=30.0, gt=0, le=60.0)
    relax_teacher_load_limits: bool = False
    require_optimal: bool = True
    # New: debug capacity tables and smart relaxation mode
    debug_capacity_mode: bool = False
    smart_relaxation: bool = False
    # Extended solve: if FEASIBLE after the initial budget, re-run with 2x time
    allow_extended_solve: bool = False
    # Optional hybrid initialization (GA-style warm start for CP-SAT)
    hybrid_init_enabled: bool = False
    hybrid_population_size: int = Field(default=24, ge=4, le=200)
    hybrid_generations: int = Field(default=20, ge=1, le=500)
    multi_seed_restarts: int = Field(default=1, ge=1, le=3)
    lns_iterations: int = Field(default=0, ge=0, le=5)
    lns_keep_fraction: float = Field(default=0.7, ge=0.0, le=1.0)


class SolveGlobalTimetableRequest(GenerateGlobalTimetableRequest):
    max_time_seconds: float = Field(default=30.0, gt=0, le=60.0)
    relax_teacher_load_limits: bool = False
    require_optimal: bool = True
    debug_capacity_mode: bool = False
    smart_relaxation: bool = False
    # Extended solve: if FEASIBLE after the initial budget, re-run with 2x time
    allow_extended_solve: bool = False
    # Optional hybrid initialization (GA-style warm start for CP-SAT)
    hybrid_init_enabled: bool = False
    hybrid_population_size: int = Field(default=24, ge=4, le=200)
    hybrid_generations: int = Field(default=20, ge=1, le=500)
    multi_seed_restarts: int = Field(default=1, ge=1, le=3)
    lns_iterations: int = Field(default=0, ge=0, le=5)
    lns_keep_fraction: float = Field(default=0.7, ge=0.0, le=1.0)


class SolverConflict(BaseModel):
    id: uuid.UUID | None = None
    severity: Literal["INFO", "WARN", "ERROR"] = "ERROR"
    conflict_type: str
    message: str
    section_id: uuid.UUID | None = None
    teacher_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    slot_id: uuid.UUID | None = None
    # New structured payload for UI drill-down. Prefer this over `metadata`.
    details: dict[str, Any] = Field(default_factory=dict)
    # Legacy: kept so older frontend builds still work.
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateTimetableResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["FAILED_VALIDATION", "READY_FOR_SOLVE"]
    conflicts: list[SolverConflict] = Field(default_factory=list)


class SolveTimetableResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["RUNNING", "FAILED_VALIDATION", "INFEASIBLE", "FEASIBLE", "SUBOPTIMAL", "OPTIMAL", "ERROR"]
    entries_written: int = 0
    conflicts: list[SolverConflict] = Field(default_factory=list)

    # Extended solver result details
    reason_summary: str | None = None
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    objective_score: int | None = None
    improvements_possible: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    soft_conflicts: list[SolverConflict] = Field(default_factory=list)
    solver_stats: dict[str, Any] = Field(default_factory=dict)
    # New: minimal relaxation suggestions when infeasible due to capacity
    minimal_relaxation: list[dict[str, Any]] = Field(default_factory=list)
    # Time-budget result fields
    best_bound: int | None = None
    optimality_gap: int | None = None
    solve_time_seconds: float | None = None
    message: str | None = None


class RunSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: str
    solver_version: str | None = None
    seed: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class RunDetail(RunSummary):
    conflicts_total: int = 0
    entries_total: int = 0
    lns_telemetry: dict[str, Any] | None = None


class TeacherLoadAdjustmentRow(BaseModel):
    teacher_id: uuid.UUID | None = None
    teacher_code: str | None = None
    teacher_name: str | None = None
    required_load: int
    preferred_limit: int
    assigned_load: int
    effective_limit: int
    overload: int
    # Backward-compatible aliases for older clients.
    original_limit: int | None = None
    extended_limit: int | None = None


class TeacherLoadAdjustmentReportResponse(BaseModel):
    run_id: uuid.UUID
    total_teachers: int = 0
    adjusted_teachers: int = 0
    overloaded_teachers: int = 0
    rows: list[TeacherLoadAdjustmentRow] = Field(default_factory=list)


class RoomCapacityIssueRow(BaseModel):
    conflict_id: uuid.UUID | None = None
    severity: Literal["INFO", "WARN", "ERROR"] = "ERROR"
    conflict_type: str
    message: str
    slot_id: uuid.UUID | None = None
    room_type: str | None = None
    required: int | None = None
    available: int | None = None
    shortage: int | None = None
    affected_slots: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class RoomCapacityReportResponse(BaseModel):
    run_id: uuid.UUID
    total_issues: int = 0
    error_issues: int = 0
    warning_issues: int = 0
    rows: list[RoomCapacityIssueRow] = Field(default_factory=list)


class TimetableEntryOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID

    section_id: uuid.UUID
    section_code: str
    section_name: str

    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    subject_type: str

    teacher_id: uuid.UUID
    teacher_code: str
    teacher_name: str

    room_id: uuid.UUID
    room_code: str
    room_name: str
    room_type: str

    slot_id: uuid.UUID
    day_of_week: int
    slot_index: int
    start_time: str
    end_time: str
    duration_slots: int = 1
    is_block_start: bool = True
    block_start_slot_index: int | None = None
    block_end_slot_index: int | None = None
    block_end_time: str | None = None

    combined_class_id: uuid.UUID | None = None
    elective_block_id: uuid.UUID | None = None
    elective_block_name: str | None = None
    created_at: datetime


class ListRunsResponse(BaseModel):
    runs: list[RunSummary] = Field(default_factory=list)


class ListRunEntriesResponse(BaseModel):
    run_id: uuid.UUID
    entries: list[TimetableEntryOut] = Field(default_factory=list)


class ListRunConflictsResponse(BaseModel):
    run_id: uuid.UUID
    conflicts: list[SolverConflict] = Field(default_factory=list)


class TimeSlotOut(BaseModel):
    id: uuid.UUID
    day_of_week: int
    slot_index: int
    start_time: str
    end_time: str
    is_lunch_break: bool = False


class ListTimeSlotsResponse(BaseModel):
    slots: list[TimeSlotOut] = Field(default_factory=list)


class FixedTimetableEntryOut(BaseModel):
    id: uuid.UUID

    section_id: uuid.UUID
    section_code: str
    section_name: str

    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    subject_type: str

    teacher_id: uuid.UUID
    teacher_code: str
    teacher_name: str

    room_id: uuid.UUID
    room_code: str
    room_name: str
    room_type: str

    slot_id: uuid.UUID
    day_of_week: int
    slot_index: int
    start_time: str
    end_time: str

    is_active: bool
    created_at: datetime


class ListFixedTimetableEntriesResponse(BaseModel):
    entries: list[FixedTimetableEntryOut] = Field(default_factory=list)


class UpsertFixedTimetableEntryRequest(BaseModel):
    section_id: uuid.UUID
    subject_id: uuid.UUID
    teacher_id: uuid.UUID
    room_id: uuid.UUID
    slot_id: uuid.UUID


class SpecialAllotmentOut(BaseModel):
    id: uuid.UUID

    section_id: uuid.UUID
    section_code: str
    section_name: str
    combined_group_id: uuid.UUID | None = None
    target_kind: Literal["SECTION", "COMBINED_GROUP"] = "SECTION"
    target_label: str | None = None
    target_section_codes: list[str] = Field(default_factory=list)

    subject_id: uuid.UUID
    subject_code: str
    subject_name: str
    subject_type: str

    teacher_id: uuid.UUID
    teacher_code: str
    teacher_name: str

    room_id: uuid.UUID
    room_code: str
    room_name: str
    room_type: str

    slot_id: uuid.UUID
    day_of_week: int
    slot_index: int
    start_time: str
    end_time: str

    reason: str | None = None
    is_active: bool
    created_at: datetime


class ListSpecialAllotmentsResponse(BaseModel):
    entries: list[SpecialAllotmentOut] = Field(default_factory=list)


class UpsertSpecialAllotmentRequest(BaseModel):
    section_id: uuid.UUID | None = None
    combined_group_id: uuid.UUID | None = None
    subject_id: uuid.UUID
    teacher_id: uuid.UUID
    room_id: uuid.UUID
    slot_id: uuid.UUID | None = None
    reason: str | None = None


class EligibleTeacherOut(BaseModel):
    id: uuid.UUID
    code: str
    full_name: str
    weekly_off_day: int | None = None


class ListEligibleTeachersResponse(BaseModel):
    subject_id: uuid.UUID
    teachers: list[EligibleTeacherOut] = Field(default_factory=list)


# ── Timetable Validation ────────────────────────────────────────────────────


class ValidateTimetableRequest(BaseModel):
    """Request body for POST /api/solver/validate."""

    program_code: str = Field(min_length=1)
    academic_year_number: int | None = None  # None = all years (program-wide)


class ValidationIssue(BaseModel):
    """One capacity / feasibility issue returned by the validate endpoint."""

    type: str
    resource: str | None = None
    resource_type: str | None = None
    # Entity identifiers for drill-down
    teacher_id: str | None = None
    teacher: str | None = None
    section_id: str | None = None
    section: str | None = None
    subject_id: str | None = None
    subject: str | None = None
    # Numeric analysis
    required: int | None = None
    capacity: int | None = None
    shortage: int | None = None
    # Optional contributor breakdown (e.g. which subjects load a teacher)
    contributors: list[dict[str, Any]] = Field(default_factory=list)
    # Human-readable suggested fix
    suggestion: str | None = None


class ValidateTimetableResponse(BaseModel):
    """Response from POST /api/solver/validate."""

    status: Literal["VALID", "WARNINGS", "INVALID"]
    # Structural / prerequisite errors that block solving
    errors: list[SolverConflict] = Field(default_factory=list)
    # Non-blocking warnings
    warnings: list[SolverConflict] = Field(default_factory=list)
    # Capacity / feasibility issues (teacher overload, room shortage, etc.)
    capacity_issues: list[ValidationIssue] = Field(default_factory=list)
    # Raw capacity summary numbers for debugging
    summary: dict[str, Any] = Field(default_factory=dict)


class TeacherLoadCalculationRow(BaseModel):
    teacher_id: str
    teacher_name: str
    required_lectures: int
    max_lectures_limit: int
    overload: int


class SectionCalculationRow(BaseModel):
    section_id: str
    section_code: str
    total_classes_required: int
    available_slots: int
    infeasible: bool = False
    shortage: int = 0


class RoomAnalysisSummary(BaseModel):
    total_rooms: int
    parallel_required: int
    deficit: int
    lab_required_slots: int = 0
    lab_available_slots: int = 0
    lab_rooms: int = 0


class UtilizationSummary(BaseModel):
    total_slots: int
    total_required_classes: int
    total_capacity: int
    percentage: float


class SolverCalculationsResponse(BaseModel):
    teacher_load: list[TeacherLoadCalculationRow] = Field(default_factory=list)
    section_summary: list[SectionCalculationRow] = Field(default_factory=list)
    room_analysis: RoomAnalysisSummary
    utilization: UtilizationSummary
    bottlenecks: list[str] = Field(default_factory=list)
    capacity_summary: dict[str, Any] = Field(default_factory=dict)

