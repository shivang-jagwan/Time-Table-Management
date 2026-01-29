from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session

from api.deps import require_admin
from core.db import (
    DatabaseUnavailableError,
    get_db,
    is_transient_db_connectivity_error,
    validate_db_connection,
)
from models.academic_year import AcademicYear
from models.program import Program
from models.room import Room
from models.section import Section
from models.section_elective import SectionElective
from models.section_subject import SectionSubject
from models.section_time_window import SectionTimeWindow
from models.subject import Subject
from models.teacher import Teacher
from models.teacher_subject_section import TeacherSubjectSection
from models.time_slot import TimeSlot
from models.timetable_conflict import TimetableConflict
from models.timetable_entry import TimetableEntry
from models.timetable_run import TimetableRun
from models.fixed_timetable_entry import FixedTimetableEntry
from models.track_subject import TrackSubject
from models.elective_block import ElectiveBlock
from schemas.solver import (
    GenerateTimetableRequest,
    GenerateGlobalTimetableRequest,
    GenerateTimetableResponse,
    ListRunConflictsResponse,
    ListRunEntriesResponse,
    ListRunsResponse,
    RunDetail,
    RunSummary,
    ListTimeSlotsResponse,
    SolveTimetableRequest,
    SolveGlobalTimetableRequest,
    SolveTimetableResponse,
    SolverConflict,
    TimetableEntryOut,
    TimeSlotOut,
    FixedTimetableEntryOut,
    ListFixedTimetableEntriesResponse,
    UpsertFixedTimetableEntryRequest,
)
from schemas.subject import SubjectOut
from services.solver_validation import validate_prereqs
from solver.cp_sat_solver import solve_program_global, solve_program_year


router = APIRouter()


def _required_subject_ids_for_section(db: Session, *, program_id: uuid.UUID, section: Section) -> list[uuid.UUID]:
    # Explicit mapping overrides any curriculum inference.
    mapped = (
        db.execute(select(SectionSubject.subject_id).where(SectionSubject.section_id == section.id))
        .scalars()
        .all()
    )
    if mapped:
        return list(mapped)

    # Track curriculum (+ elective selection)
    track_rows = (
        db.execute(
            select(TrackSubject)
            .where(TrackSubject.program_id == program_id)
            .where(TrackSubject.academic_year_id == section.academic_year_id)
            .where(TrackSubject.track == section.track)
        )
        .scalars()
        .all()
    )
    mandatory = [r for r in track_rows if not r.is_elective]
    elective_options = [r for r in track_rows if r.is_elective]

    subject_ids: list[uuid.UUID] = [r.subject_id for r in mandatory]
    if elective_options:
        sel = (
            db.execute(select(SectionElective).where(SectionElective.section_id == section.id))
            .scalars()
            .first()
        )
        if sel is not None:
            subject_ids.append(sel.subject_id)
    return subject_ids


def _validate_fixed_entry_refs(
    db: Session,
    *,
    section: Section,
    subject: Subject,
    teacher: Teacher,
    room: Room,
    slot: TimeSlot,
) -> None:
    if subject.program_id != section.program_id:
        raise HTTPException(status_code=400, detail="SUBJECT_PROGRAM_MISMATCH")
    if getattr(subject, "academic_year_id", None) != getattr(section, "academic_year_id", None):
        raise HTTPException(status_code=400, detail="SUBJECT_ACADEMIC_YEAR_MISMATCH")
    if not bool(subject.is_active):
        raise HTTPException(status_code=400, detail="SUBJECT_NOT_ACTIVE")
    if not bool(teacher.is_active):
        raise HTTPException(status_code=400, detail="TEACHER_NOT_ACTIVE")
    if not bool(room.is_active):
        raise HTTPException(status_code=400, detail="ROOM_NOT_ACTIVE")

    # Section must be working at this slot (time window).
    w = (
        db.execute(
            select(SectionTimeWindow)
            .where(SectionTimeWindow.section_id == section.id)
            .where(SectionTimeWindow.day_of_week == int(slot.day_of_week))
        )
        .scalars()
        .first()
    )
    if w is None:
        raise HTTPException(status_code=400, detail="SLOT_OUTSIDE_SECTION_WINDOW")
    if int(slot.slot_index) < int(w.start_slot_index) or int(slot.slot_index) > int(w.end_slot_index):
        raise HTTPException(status_code=400, detail="SLOT_OUTSIDE_SECTION_WINDOW")

    # Teacher off-day must not be violated.
    if teacher.weekly_off_day is not None and int(teacher.weekly_off_day) == int(slot.day_of_week):
        raise HTTPException(status_code=400, detail="TEACHER_WEEKLY_OFF_DAY")

    # Strict assignment: teacher must be assigned to (section, subject).
    assigned = (
        db.execute(
            select(TeacherSubjectSection.id)
            .where(TeacherSubjectSection.teacher_id == teacher.id)
            .where(TeacherSubjectSection.subject_id == subject.id)
            .where(TeacherSubjectSection.section_id == section.id)
            .where(TeacherSubjectSection.is_active.is_(True))
            .limit(1)
        ).first()
        is not None
    )
    if not assigned:
        raise HTTPException(status_code=400, detail="TEACHER_NOT_ASSIGNED_TO_SECTION_SUBJECT")

    # LAB block must fit (entry represents LAB start).
    if str(subject.subject_type) == "LAB":
        block = int(getattr(subject, "lab_block_size_slots", 1) or 1)
        if block < 1:
            block = 1

        # Need a window that covers the full block on the same day.
        end_idx = int(slot.slot_index) + block - 1
        if end_idx > int(w.end_slot_index):
            raise HTTPException(status_code=400, detail="LAB_BLOCK_DOES_NOT_FIT")

        # Ensure all covered time slots exist (contiguous indices).
        for j in range(block):
            si = int(slot.slot_index) + j
            exists = (
                db.execute(
                    select(TimeSlot.id)
                    .where(TimeSlot.day_of_week == int(slot.day_of_week))
                    .where(TimeSlot.slot_index == int(si))
                    .limit(1)
                ).first()
                is not None
            )
            if not exists:
                raise HTTPException(status_code=400, detail="LAB_BLOCK_SLOT_MISSING")


@router.get("/section-required-subjects", response_model=list[SubjectOut])
def list_required_subjects_for_section(
    section_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    section = db.get(Section, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="SECTION_NOT_FOUND")

    subject_ids = _required_subject_ids_for_section(db, program_id=section.program_id, section=section)
    if not subject_ids:
        return []

    subjects = (
        db.execute(select(Subject).where(Subject.id.in_(subject_ids)).order_by(Subject.code.asc()))
        .scalars()
        .all()
    )
    return subjects


@router.get("/assigned-teacher")
def get_assigned_teacher(
    section_id: uuid.UUID,
    subject_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Return the strictly assigned teacher for a section+subject (if any)."""
    row = (
        db.execute(
            select(Teacher)
            .join(TeacherSubjectSection, TeacherSubjectSection.teacher_id == Teacher.id)
            .where(TeacherSubjectSection.section_id == section_id)
            .where(TeacherSubjectSection.subject_id == subject_id)
            .where(TeacherSubjectSection.is_active.is_(True))
            .where(Teacher.is_active.is_(True))
            .limit(1)
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="TEACHER_ASSIGNMENT_NOT_FOUND")
    return {
        "teacher_id": row.id,
        "teacher_code": row.code,
        "teacher_name": row.full_name,
        "weekly_off_day": int(row.weekly_off_day) if row.weekly_off_day is not None else None,
    }


@router.get("/fixed-entries", response_model=ListFixedTimetableEntriesResponse)
def list_fixed_entries(
    section_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    section = db.get(Section, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="SECTION_NOT_FOUND")

    q = (
        select(FixedTimetableEntry, Section, Subject, Teacher, Room, TimeSlot)
        .join(Section, Section.id == FixedTimetableEntry.section_id)
        .join(Subject, Subject.id == FixedTimetableEntry.subject_id)
        .join(Teacher, Teacher.id == FixedTimetableEntry.teacher_id)
        .join(Room, Room.id == FixedTimetableEntry.room_id)
        .join(TimeSlot, TimeSlot.id == FixedTimetableEntry.slot_id)
        .where(FixedTimetableEntry.section_id == section_id)
    )
    if not include_inactive:
        q = q.where(FixedTimetableEntry.is_active.is_(True))
    q = q.order_by(TimeSlot.day_of_week.asc(), TimeSlot.slot_index.asc())

    rows = db.execute(q).all()
    out: list[FixedTimetableEntryOut] = []
    for fe, sec, subj, teacher, room, slot in rows:
        out.append(
            FixedTimetableEntryOut(
                id=fe.id,
                section_id=sec.id,
                section_code=sec.code,
                section_name=sec.name,
                subject_id=subj.id,
                subject_code=subj.code,
                subject_name=subj.name,
                subject_type=str(subj.subject_type),
                teacher_id=teacher.id,
                teacher_code=teacher.code,
                teacher_name=teacher.full_name,
                room_id=room.id,
                room_code=room.code,
                room_name=room.name,
                room_type=str(room.room_type),
                slot_id=slot.id,
                day_of_week=int(slot.day_of_week),
                slot_index=int(slot.slot_index),
                start_time=slot.start_time.strftime("%H:%M"),
                end_time=slot.end_time.strftime("%H:%M"),
                is_active=bool(fe.is_active),
                created_at=fe.created_at,
            )
        )
    return ListFixedTimetableEntriesResponse(entries=out)


@router.post("/fixed-entries", response_model=FixedTimetableEntryOut)
def upsert_fixed_entry(
    payload: UpsertFixedTimetableEntryRequest,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    section = db.get(Section, payload.section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="SECTION_NOT_FOUND")
    subject = db.get(Subject, payload.subject_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="SUBJECT_NOT_FOUND")
    teacher = db.get(Teacher, payload.teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="TEACHER_NOT_FOUND")
    room = db.get(Room, payload.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")
    slot = db.get(TimeSlot, payload.slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="SLOT_NOT_FOUND")

    allowed_subject_ids = set(_required_subject_ids_for_section(db, program_id=section.program_id, section=section))
    if allowed_subject_ids and subject.id not in allowed_subject_ids:
        raise HTTPException(status_code=400, detail="SUBJECT_NOT_ALLOWED_FOR_SECTION")

    _validate_fixed_entry_refs(db, section=section, subject=subject, teacher=teacher, room=room, slot=slot)

    # Upsert by (section, slot)
    existing = (
        db.execute(
            select(FixedTimetableEntry)
            .where(FixedTimetableEntry.section_id == payload.section_id)
            .where(FixedTimetableEntry.slot_id == payload.slot_id)
            .where(FixedTimetableEntry.is_active.is_(True))
        )
        .scalars()
        .first()
    )
    if existing is None:
        existing = FixedTimetableEntry(
            section_id=payload.section_id,
            subject_id=payload.subject_id,
            teacher_id=payload.teacher_id,
            room_id=payload.room_id,
            slot_id=payload.slot_id,
            is_active=True,
        )
        db.add(existing)
    else:
        existing.subject_id = payload.subject_id
        existing.teacher_id = payload.teacher_id
        existing.room_id = payload.room_id

    db.commit()

    # Re-read via join for output.
    row = (
        db.execute(
            select(FixedTimetableEntry, Section, Subject, Teacher, Room, TimeSlot)
            .join(Section, Section.id == FixedTimetableEntry.section_id)
            .join(Subject, Subject.id == FixedTimetableEntry.subject_id)
            .join(Teacher, Teacher.id == FixedTimetableEntry.teacher_id)
            .join(Room, Room.id == FixedTimetableEntry.room_id)
            .join(TimeSlot, TimeSlot.id == FixedTimetableEntry.slot_id)
            .where(FixedTimetableEntry.id == existing.id)
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=500, detail="FIXED_ENTRY_WRITE_FAILED")
    fe, sec, subj, teacher, room, slot = row
    return FixedTimetableEntryOut(
        id=fe.id,
        section_id=sec.id,
        section_code=sec.code,
        section_name=sec.name,
        subject_id=subj.id,
        subject_code=subj.code,
        subject_name=subj.name,
        subject_type=str(subj.subject_type),
        teacher_id=teacher.id,
        teacher_code=teacher.code,
        teacher_name=teacher.full_name,
        room_id=room.id,
        room_code=room.code,
        room_name=room.name,
        room_type=str(room.room_type),
        slot_id=slot.id,
        day_of_week=int(slot.day_of_week),
        slot_index=int(slot.slot_index),
        start_time=slot.start_time.strftime("%H:%M"),
        end_time=slot.end_time.strftime("%H:%M"),
        is_active=bool(fe.is_active),
        created_at=fe.created_at,
    )


@router.delete("/fixed-entries/{entry_id}")
def delete_fixed_entry(
    entry_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(FixedTimetableEntry, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="FIXED_ENTRY_NOT_FOUND")
    row.is_active = False
    db.commit()
    return {"ok": True}


def _get_academic_year(db: Session, year_number: int) -> AcademicYear:
    ay = db.execute(select(AcademicYear).where(AcademicYear.year_number == int(year_number))).scalar_one_or_none()
    if ay is None:
        raise HTTPException(status_code=404, detail="ACADEMIC_YEAR_NOT_FOUND")
    return ay


@router.get("/time-slots", response_model=ListTimeSlotsResponse)
def list_time_slots(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    slots = (
        db.execute(select(TimeSlot).order_by(TimeSlot.day_of_week.asc(), TimeSlot.slot_index.asc()))
        .scalars()
        .all()
    )
    return ListTimeSlotsResponse(
        slots=[
            TimeSlotOut(
                id=s.id,
                day_of_week=int(s.day_of_week),
                slot_index=int(s.slot_index),
                start_time=s.start_time.strftime("%H:%M"),
                end_time=s.end_time.strftime("%H:%M"),
            )
            for s in slots
        ]
    )


@router.get("/runs", response_model=ListRunsResponse)
def list_runs(
    program_code: str | None = Query(default=None),
    academic_year_number: int | None = Query(default=None, ge=1, le=4),
    limit: int = Query(default=50, ge=1, le=200),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(select(TimetableRun).order_by(TimetableRun.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )

    runs: list[RunSummary] = []
    for r in rows:
        params = r.parameters or {}
        if program_code is not None and params.get("program_code") != program_code:
            continue
        if academic_year_number is not None and params.get("academic_year_number") != academic_year_number:
            continue
        runs.append(
            RunSummary(
                id=r.id,
                created_at=r.created_at,
                status=str(r.status),
                solver_version=r.solver_version,
                seed=r.seed,
                parameters=params,
                notes=r.notes,
            )
        )

    return ListRunsResponse(runs=runs)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(
    run_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = db.execute(select(TimetableRun).where(TimetableRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")

    conflicts_total = (
        db.execute(select(func.count(TimetableConflict.id)).where(TimetableConflict.run_id == run_id)).scalar_one()
        or 0
    )
    entries_total = (
        db.execute(select(func.count(TimetableEntry.id)).where(TimetableEntry.run_id == run_id)).scalar_one() or 0
    )

    return RunDetail(
        id=run.id,
        created_at=run.created_at,
        status=str(run.status),
        solver_version=run.solver_version,
        seed=run.seed,
        parameters=run.parameters or {},
        notes=run.notes,
        conflicts_total=int(conflicts_total),
        entries_total=int(entries_total),
    )


@router.get("/runs/{run_id}/conflicts", response_model=ListRunConflictsResponse)
def list_run_conflicts(
    run_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = db.execute(select(TimetableRun.id).where(TimetableRun.id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")

    rows = (
        db.execute(
            select(TimetableConflict)
            .where(TimetableConflict.run_id == run_id)
            .order_by(TimetableConflict.created_at.asc())
        )
        .scalars()
        .all()
    )

    return ListRunConflictsResponse(
        run_id=run_id,
        conflicts=[
            SolverConflict(
                severity=str(c.severity),
                conflict_type=c.conflict_type,
                message=c.message,
                section_id=c.section_id,
                teacher_id=c.teacher_id,
                subject_id=c.subject_id,
                room_id=c.room_id,
                slot_id=c.slot_id,
                metadata=c.metadata_json or {},
            )
            for c in rows
        ],
    )


@router.get("/runs/{run_id}/entries", response_model=ListRunEntriesResponse)
def list_run_entries(
    run_id: uuid.UUID,
    section_code: str | None = Query(default=None),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    run = db.execute(select(TimetableRun).where(TimetableRun.id == run_id)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")

    section_id_filter: uuid.UUID | None = None
    if section_code is not None:
        params = run.parameters or {}
        program_code = params.get("program_code")
        academic_year_number = params.get("academic_year_number")
        if not program_code:
            raise HTTPException(status_code=422, detail="RUN_MISSING_PARAMETERS")
        program = db.execute(select(Program).where(Program.code == program_code)).scalar_one_or_none()
        if program is None:
            raise HTTPException(status_code=422, detail="RUN_PROGRAM_NOT_FOUND")

        year_id: uuid.UUID | None = None
        if academic_year_number is not None:
            year_id = _get_academic_year(db, int(academic_year_number)).id
        elif getattr(run, "academic_year_id", None) is not None:
            year_id = run.academic_year_id

        q_section = select(Section).where(Section.program_id == program.id).where(Section.code == section_code)
        if year_id is not None:
            q_section = q_section.where(Section.academic_year_id == year_id)
        section = db.execute(q_section.order_by(Section.created_at.desc())).scalars().first()
        if section is None:
            raise HTTPException(status_code=404, detail="SECTION_NOT_FOUND")
        section_id_filter = section.id

    q = (
        select(TimetableEntry, Section, Subject, Teacher, Room, TimeSlot, ElectiveBlock)
        .join(Section, Section.id == TimetableEntry.section_id)
        .join(Subject, Subject.id == TimetableEntry.subject_id)
        .join(Teacher, Teacher.id == TimetableEntry.teacher_id)
        .join(Room, Room.id == TimetableEntry.room_id)
        .join(TimeSlot, TimeSlot.id == TimetableEntry.slot_id)
        .outerjoin(ElectiveBlock, ElectiveBlock.id == TimetableEntry.elective_block_id)
        .where(TimetableEntry.run_id == run_id)
    )
    if section_id_filter is not None:
        q = q.where(TimetableEntry.section_id == section_id_filter)

    q = q.order_by(Section.code.asc(), TimeSlot.day_of_week.asc(), TimeSlot.slot_index.asc())

    rows = db.execute(q).all()
    entries: list[TimetableEntryOut] = []
    for te, sec, subj, teacher, room, slot, eb in rows:
        entries.append(
            TimetableEntryOut(
                id=te.id,
                run_id=te.run_id,
                section_id=sec.id,
                section_code=sec.code,
                section_name=sec.name,
                subject_id=subj.id,
                subject_code=subj.code,
                subject_name=subj.name,
                subject_type=str(subj.subject_type),
                teacher_id=teacher.id,
                teacher_code=teacher.code,
                teacher_name=teacher.full_name,
                room_id=room.id,
                room_code=room.code,
                room_name=room.name,
                room_type=str(room.room_type),
                slot_id=slot.id,
                day_of_week=int(slot.day_of_week),
                slot_index=int(slot.slot_index),
                start_time=slot.start_time.strftime("%H:%M"),
                end_time=slot.end_time.strftime("%H:%M"),
                combined_class_id=te.combined_class_id,
                elective_block_id=getattr(te, "elective_block_id", None),
                elective_block_name=(eb.name if eb is not None else None),
                created_at=te.created_at,
            )
        )

    return ListRunEntriesResponse(run_id=run_id, entries=entries)


@router.post("/generate", response_model=GenerateTimetableResponse)
def generate_timetable(
    payload: GenerateTimetableRequest,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        # Explicit connectivity validation before creating any rows.
        validate_db_connection(db)

        ay = _get_academic_year(db, int(payload.academic_year_number))

        run = TimetableRun(
            academic_year_id=ay.id,
            seed=payload.seed,
            status="CREATED",
            parameters={
                "program_code": payload.program_code,
                "academic_year_number": payload.academic_year_number,
                "scope": "ACADEMIC_YEAR",
            },
        )
        db.add(run)
        db.flush()  # assign run.id

        program = db.execute(select(Program).where(Program.code == payload.program_code)).scalar_one_or_none()
        if program is None:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="PROGRAM_NOT_FOUND",
                        message=f"Unknown program_code '{payload.program_code}'.",
                    )
                ],
            )

        sections = (
            db.execute(
                select(Section)
                .where(Section.program_id == program.id)
                .where(Section.academic_year_id == ay.id)
                .where(Section.is_active.is_(True))
                .order_by(Section.code)
            )
            .scalars()
            .all()
        )
        if not sections:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="NO_ACTIVE_SECTIONS",
                        message=f"No active sections found for program '{payload.program_code}' year {payload.academic_year_number}.",
                    )
                ],
            )

        conflicts = validate_prereqs(
            db,
            run=run,
            program_id=program.id,
            academic_year_id=ay.id,
            sections=sections,
        )
        errors = [c for c in conflicts if str(c.severity).upper() != "WARN"]
        warnings = [c for c in conflicts if str(c.severity).upper() == "WARN"]
        if errors:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in conflicts
                ],
            )

        # Validations passed; actual solve will happen in the next phase.
        run.status = "CREATED"
        db.commit()
        return GenerateTimetableResponse(
            run_id=run.id,
            status="READY_FOR_SOLVE",
            conflicts=[
                SolverConflict(
                    severity=c.severity,
                    conflict_type=c.conflict_type,
                    message=c.message,
                    section_id=c.section_id,
                    teacher_id=c.teacher_id,
                    subject_id=c.subject_id,
                    room_id=c.room_id,
                    slot_id=c.slot_id,
                    metadata=c.metadata or {},
                )
                for c in warnings
            ],
        )

    except DatabaseUnavailableError:
        db.rollback()
        raise
    except SAOperationalError as exc:
        db.rollback()
        if is_transient_db_connectivity_error(exc):
            raise DatabaseUnavailableError("Database temporarily unavailable") from exc
        raise


@router.post("/generate-global", response_model=GenerateTimetableResponse)
def generate_timetable_global(
    payload: GenerateGlobalTimetableRequest,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Program-wide generate endpoint.

    Creates a run and performs validations for a full-program solve (all years).
    """
    try:
        validate_db_connection(db)

        run = TimetableRun(
            academic_year_id=None,
            seed=payload.seed,
            status="CREATED",
            parameters={
                "program_code": payload.program_code,
                "scope": "PROGRAM_GLOBAL",
            },
        )
        db.add(run)
        db.flush()

        program = db.execute(select(Program).where(Program.code == payload.program_code)).scalar_one_or_none()
        if program is None:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="PROGRAM_NOT_FOUND",
                        message=f"Unknown program_code '{payload.program_code}'.",
                    )
                ],
            )

        sections = (
            db.execute(
                select(Section)
                .where(Section.program_id == program.id)
                .where(Section.is_active.is_(True))
                .order_by(Section.code)
            )
            .scalars()
            .all()
        )
        if not sections:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="NO_ACTIVE_SECTIONS",
                        message=f"No active sections found for program '{payload.program_code}'.",
                    )
                ],
            )

        run.parameters = {
            **(run.parameters or {}),
            "academic_year_ids": sorted({str(s.academic_year_id) for s in sections}),
        }

        conflicts = validate_prereqs(
            db,
            run=run,
            program_id=program.id,
            academic_year_id=None,
            sections=sections,
        )
        errors = [c for c in conflicts if str(c.severity).upper() != "WARN"]
        warnings = [c for c in conflicts if str(c.severity).upper() == "WARN"]
        if errors:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return GenerateTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in conflicts
                ],
            )

        run.status = "CREATED"
        db.commit()
        return GenerateTimetableResponse(
            run_id=run.id,
            status="READY_FOR_SOLVE",
            conflicts=[
                SolverConflict(
                    severity=c.severity,
                    conflict_type=c.conflict_type,
                    message=c.message,
                    section_id=c.section_id,
                    teacher_id=c.teacher_id,
                    subject_id=c.subject_id,
                    room_id=c.room_id,
                    slot_id=c.slot_id,
                    metadata=c.metadata or {},
                )
                for c in warnings
            ],
        )

    except DatabaseUnavailableError:
        db.rollback()
        raise
    except SAOperationalError as exc:
        db.rollback()
        if is_transient_db_connectivity_error(exc):
            raise DatabaseUnavailableError("Database temporarily unavailable") from exc
        raise


@router.post("/solve", response_model=SolveTimetableResponse)
def solve_timetable(
    payload: SolveTimetableRequest,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        # Explicit connectivity validation before creating any rows.
        validate_db_connection(db)

        ay = _get_academic_year(db, int(payload.academic_year_number))

        run = TimetableRun(
            academic_year_id=ay.id,
            seed=payload.seed,
            status="CREATED",
            parameters={
                "program_code": payload.program_code,
                "academic_year_number": payload.academic_year_number,
                "max_time_seconds": payload.max_time_seconds,
                "relax_teacher_load_limits": payload.relax_teacher_load_limits,
                "scope": "ACADEMIC_YEAR",
            },
        )
        db.add(run)
        db.flush()

        program = db.execute(select(Program).where(Program.code == payload.program_code)).scalar_one_or_none()
        if program is None:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="PROGRAM_NOT_FOUND",
                        message=f"Unknown program_code '{payload.program_code}'.",
                    )
                ],
            )

        sections = (
            db.execute(
                select(Section)
                .where(Section.program_id == program.id)
                .where(Section.academic_year_id == ay.id)
                .where(Section.is_active.is_(True))
                .order_by(Section.code)
            )
            .scalars()
            .all()
        )
        if not sections:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="NO_ACTIVE_SECTIONS",
                        message=f"No active sections found for program '{payload.program_code}' year {payload.academic_year_number}.",
                    )
                ],
            )

        conflicts = validate_prereqs(
            db,
            run=run,
            program_id=program.id,
            academic_year_id=ay.id,
            sections=sections,
        )
        errors = [c for c in conflicts if str(c.severity).upper() != "WARN"]
        warnings = [c for c in conflicts if str(c.severity).upper() == "WARN"]
        if errors:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in conflicts
                ],
            )

        if payload.relax_teacher_load_limits:
            # Persist an explicit warning so runs are auditable.
            from models.timetable_conflict import TimetableConflict

            db.add(
                TimetableConflict(
                    run_id=run.id,
                    severity="WARN",
                    conflict_type="RELAXED_TEACHER_LOAD_LIMITS",
                    message="Solved with teacher load limits disabled (max_per_day/max_per_week not enforced).",
                    metadata_json={},
                )
            )
            db.flush()

        result = solve_program_year(
            db,
            run=run,
            program_id=program.id,
            academic_year_id=ay.id,
            seed=payload.seed,
            max_time_seconds=payload.max_time_seconds,
            enforce_teacher_load_limits=not payload.relax_teacher_load_limits,
        )

        return SolveTimetableResponse(
            run_id=run.id,
            status=result.status,
            entries_written=result.entries_written,
            conflicts=(
                [
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in warnings
                ]
                + [
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in result.conflicts
                ]
            ),
        )

    except DatabaseUnavailableError:
        db.rollback()
        raise
    except SAOperationalError as exc:
        db.rollback()
        if is_transient_db_connectivity_error(exc):
            raise DatabaseUnavailableError("Database temporarily unavailable") from exc
        raise


@router.post("/solve-global", response_model=SolveTimetableResponse)
def solve_timetable_global(
    payload: SolveGlobalTimetableRequest,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Program-wide solve endpoint.

    Builds ONE CP-SAT model that schedules all active sections for the program across all academic years.
    """
    try:
        validate_db_connection(db)

        run = TimetableRun(
            academic_year_id=None,
            seed=payload.seed,
            status="CREATED",
            parameters={
                "program_code": payload.program_code,
                "max_time_seconds": payload.max_time_seconds,
                "relax_teacher_load_limits": payload.relax_teacher_load_limits,
                "scope": "PROGRAM_GLOBAL",
            },
        )
        db.add(run)
        db.flush()

        program = db.execute(select(Program).where(Program.code == payload.program_code)).scalar_one_or_none()
        if program is None:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="PROGRAM_NOT_FOUND",
                        message=f"Unknown program_code '{payload.program_code}'.",
                    )
                ],
            )

        sections = (
            db.execute(
                select(Section)
                .where(Section.program_id == program.id)
                .where(Section.is_active.is_(True))
                .order_by(Section.code)
            )
            .scalars()
            .all()
        )
        if not sections:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        conflict_type="NO_ACTIVE_SECTIONS",
                        message=f"No active sections found for program '{payload.program_code}'.",
                    )
                ],
            )

        run.parameters = {
            **(run.parameters or {}),
            "academic_year_ids": sorted({str(s.academic_year_id) for s in sections}),
        }

        conflicts = validate_prereqs(
            db,
            run=run,
            program_id=program.id,
            academic_year_id=None,
            sections=sections,
        )
        errors = [c for c in conflicts if str(c.severity).upper() != "WARN"]
        warnings = [c for c in conflicts if str(c.severity).upper() == "WARN"]
        if errors:
            run.status = "VALIDATION_FAILED"
            db.commit()
            return SolveTimetableResponse(
                run_id=run.id,
                status="FAILED_VALIDATION",
                conflicts=[
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in conflicts
                ],
            )

        if payload.relax_teacher_load_limits:
            db.add(
                TimetableConflict(
                    run_id=run.id,
                    severity="WARN",
                    conflict_type="RELAXED_TEACHER_LOAD_LIMITS",
                    message="Solved with teacher load limits disabled (max_per_day/max_per_week not enforced).",
                    metadata_json={},
                )
            )
            db.flush()

        result = solve_program_global(
            db,
            run=run,
            program_id=program.id,
            seed=payload.seed,
            max_time_seconds=payload.max_time_seconds,
            enforce_teacher_load_limits=not payload.relax_teacher_load_limits,
        )

        return SolveTimetableResponse(
            run_id=run.id,
            status=result.status,
            entries_written=result.entries_written,
            conflicts=(
                [
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in warnings
                ]
                + [
                    SolverConflict(
                        severity=c.severity,
                        conflict_type=c.conflict_type,
                        message=c.message,
                        section_id=c.section_id,
                        teacher_id=c.teacher_id,
                        subject_id=c.subject_id,
                        room_id=c.room_id,
                        slot_id=c.slot_id,
                        metadata=c.metadata or {},
                    )
                    for c in result.conflicts
                ]
            ),
        )

    except DatabaseUnavailableError:
        db.rollback()
        raise
    except SAOperationalError as exc:
        db.rollback()
        if is_transient_db_connectivity_error(exc):
            raise DatabaseUnavailableError("Database temporarily unavailable") from exc
        raise


