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
    max_time_seconds: float = Field(default=10.0, gt=0)
    relax_teacher_load_limits: bool = False


class SolveGlobalTimetableRequest(GenerateGlobalTimetableRequest):
    max_time_seconds: float = Field(default=120.0, gt=0)
    relax_teacher_load_limits: bool = False


class SolverConflict(BaseModel):
    severity: Literal["ERROR", "WARN"] = "ERROR"
    conflict_type: str
    message: str
    section_id: uuid.UUID | None = None
    teacher_id: uuid.UUID | None = None
    subject_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    slot_id: uuid.UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateTimetableResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["FAILED_VALIDATION", "READY_FOR_SOLVE"]
    conflicts: list[SolverConflict] = Field(default_factory=list)


class SolveTimetableResponse(BaseModel):
    run_id: uuid.UUID
    status: Literal["FAILED_VALIDATION", "INFEASIBLE", "FEASIBLE", "OPTIMAL", "ERROR"]
    entries_written: int = 0
    conflicts: list[SolverConflict] = Field(default_factory=list)


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


class EligibleTeacherOut(BaseModel):
    id: uuid.UUID
    code: str
    full_name: str
    weekly_off_day: int | None = None


class ListEligibleTeachersResponse(BaseModel):
    subject_id: uuid.UUID
    teachers: list[EligibleTeacherOut] = Field(default_factory=list)

