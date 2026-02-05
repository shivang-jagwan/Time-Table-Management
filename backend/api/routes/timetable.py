from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_tenant_id, require_admin
from api.tenant import get_by_id, where_tenant
from core.db import get_db
from models.academic_year import AcademicYear
from models.elective_block import ElectiveBlock
from models.room import Room
from models.section import Section
from models.subject import Subject
from models.teacher import Teacher
from models.time_slot import TimeSlot
from models.timetable_entry import TimetableEntry
from models.timetable_run import TimetableRun
from schemas.timetable import TimetableGridEntryOut


router = APIRouter()


def _pick_run_id(db: Session, *, run_id: uuid.UUID | None, tenant_id: uuid.UUID | None) -> uuid.UUID | None:
    if run_id is not None:
        q_exists = where_tenant(select(TimetableRun.id).where(TimetableRun.id == run_id), TimetableRun, tenant_id)
        exists = db.execute(q_exists).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
        return run_id

    q_runs = where_tenant(select(TimetableRun), TimetableRun, tenant_id).order_by(TimetableRun.created_at.desc()).limit(200)
    rows = db.execute(q_runs).scalars().all()

    for r in rows:
        params = r.parameters or {}
        if params.get("scope") == "PROGRAM_GLOBAL" and str(r.status) in {"FEASIBLE", "OPTIMAL"}:
            return r.id

    for r in rows:
        if str(r.status) in {"FEASIBLE", "OPTIMAL"}:
            return r.id

    return None


def _rows_to_out(rows) -> list[TimetableGridEntryOut]:
    out: list[TimetableGridEntryOut] = []
    for r in rows:
        out.append(
            TimetableGridEntryOut(
                day=int(r.day),
                slot_index=int(r.slot_index),
                start_time=r.start_time.strftime("%H:%M"),
                end_time=r.end_time.strftime("%H:%M"),
                section_code=str(r.section_code),
                subject_code=str(r.subject_code),
                teacher_name=str(r.teacher_name),
                room_code=str(r.room_code),
                year_number=int(r.year_number),
                elective_block_id=str(r.elective_block_id) if r.elective_block_id else None,
                elective_block_name=str(r.elective_block_name) if r.elective_block_name else None,
            )
        )
    return out


@router.get("/section/{section_id}", response_model=list[TimetableGridEntryOut])
def get_section_timetable(
    section_id: uuid.UUID,
    run_id: uuid.UUID | None = Query(default=None),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> list[TimetableGridEntryOut]:
    if get_by_id(db, Section, section_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="SECTION_NOT_FOUND")

    chosen_run = _pick_run_id(db, run_id=run_id, tenant_id=tenant_id)
    if chosen_run is None:
        return []

    q = (
        select(
            TimeSlot.day_of_week.label("day"),
            TimeSlot.slot_index.label("slot_index"),
            TimeSlot.start_time.label("start_time"),
            TimeSlot.end_time.label("end_time"),
            Section.code.label("section_code"),
            Subject.code.label("subject_code"),
            Teacher.full_name.label("teacher_name"),
            Room.code.label("room_code"),
            AcademicYear.year_number.label("year_number"),
            TimetableEntry.elective_block_id.label("elective_block_id"),
            ElectiveBlock.name.label("elective_block_name"),
        )
        .select_from(TimetableEntry)
        .join(TimeSlot, TimeSlot.id == TimetableEntry.slot_id)
        .join(Section, Section.id == TimetableEntry.section_id)
        .join(AcademicYear, AcademicYear.id == Section.academic_year_id)
        .join(Subject, Subject.id == TimetableEntry.subject_id)
        .join(Teacher, Teacher.id == TimetableEntry.teacher_id)
        .join(Room, Room.id == TimetableEntry.room_id)
        .outerjoin(ElectiveBlock, ElectiveBlock.id == TimetableEntry.elective_block_id)
        .where(TimetableEntry.run_id == chosen_run)
        .where(TimetableEntry.section_id == section_id)
    )
    q = where_tenant(q, TimetableEntry, tenant_id)

    rows = db.execute(q).all()
    return _rows_to_out(rows)


@router.get("/room/{room_id}", response_model=list[TimetableGridEntryOut])
def get_room_timetable(
    room_id: uuid.UUID,
    run_id: uuid.UUID | None = Query(default=None),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> list[TimetableGridEntryOut]:
    if get_by_id(db, Room, room_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")

    chosen_run = _pick_run_id(db, run_id=run_id, tenant_id=tenant_id)
    if chosen_run is None:
        return []

    q = (
        select(
            TimeSlot.day_of_week.label("day"),
            TimeSlot.slot_index.label("slot_index"),
            TimeSlot.start_time.label("start_time"),
            TimeSlot.end_time.label("end_time"),
            Section.code.label("section_code"),
            Subject.code.label("subject_code"),
            Teacher.full_name.label("teacher_name"),
            Room.code.label("room_code"),
            AcademicYear.year_number.label("year_number"),
            TimetableEntry.elective_block_id.label("elective_block_id"),
            ElectiveBlock.name.label("elective_block_name"),
        )
        .select_from(TimetableEntry)
        .join(TimeSlot, TimeSlot.id == TimetableEntry.slot_id)
        .join(Section, Section.id == TimetableEntry.section_id)
        .join(AcademicYear, AcademicYear.id == Section.academic_year_id)
        .join(Subject, Subject.id == TimetableEntry.subject_id)
        .join(Teacher, Teacher.id == TimetableEntry.teacher_id)
        .join(Room, Room.id == TimetableEntry.room_id)
        .outerjoin(ElectiveBlock, ElectiveBlock.id == TimetableEntry.elective_block_id)
        .where(TimetableEntry.run_id == chosen_run)
        .where(TimetableEntry.room_id == room_id)
    )
    q = where_tenant(q, TimetableEntry, tenant_id)

    rows = db.execute(q).all()
    return _rows_to_out(rows)


@router.get("/faculty/{teacher_id}", response_model=list[TimetableGridEntryOut])
def get_faculty_timetable(
    teacher_id: uuid.UUID,
    run_id: uuid.UUID | None = Query(default=None),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> list[TimetableGridEntryOut]:
    if get_by_id(db, Teacher, teacher_id, tenant_id) is None:
        raise HTTPException(status_code=404, detail="TEACHER_NOT_FOUND")

    chosen_run = _pick_run_id(db, run_id=run_id, tenant_id=tenant_id)
    if chosen_run is None:
        return []

    q = (
        select(
            TimeSlot.day_of_week.label("day"),
            TimeSlot.slot_index.label("slot_index"),
            TimeSlot.start_time.label("start_time"),
            TimeSlot.end_time.label("end_time"),
            Section.code.label("section_code"),
            Subject.code.label("subject_code"),
            Teacher.full_name.label("teacher_name"),
            Room.code.label("room_code"),
            AcademicYear.year_number.label("year_number"),
            TimetableEntry.elective_block_id.label("elective_block_id"),
            ElectiveBlock.name.label("elective_block_name"),
        )
        .select_from(TimetableEntry)
        .join(TimeSlot, TimeSlot.id == TimetableEntry.slot_id)
        .join(Section, Section.id == TimetableEntry.section_id)
        .join(AcademicYear, AcademicYear.id == Section.academic_year_id)
        .join(Subject, Subject.id == TimetableEntry.subject_id)
        .join(Teacher, Teacher.id == TimetableEntry.teacher_id)
        .join(Room, Room.id == TimetableEntry.room_id)
        .outerjoin(ElectiveBlock, ElectiveBlock.id == TimetableEntry.elective_block_id)
        .where(TimetableEntry.run_id == chosen_run)
        .where(TimetableEntry.teacher_id == teacher_id)
    )
    q = where_tenant(q, TimetableEntry, tenant_id)

    rows = db.execute(q).all()
    return _rows_to_out(rows)
