from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import require_admin
from core.db import get_db
from models.academic_year import AcademicYear
from models.program import Program
from models.subject import Subject
from models.track_subject import TrackSubject
from schemas.curriculum import TrackSubjectCreate, TrackSubjectOut, TrackSubjectUpdate


router = APIRouter()


def _get_program(db: Session, program_code: str) -> Program:
    program = db.execute(select(Program).where(Program.code == program_code)).scalar_one_or_none()
    if program is None:
        raise HTTPException(status_code=404, detail="PROGRAM_NOT_FOUND")
    return program


def _get_academic_year(db: Session, year_number: int) -> AcademicYear:
    ay = db.execute(select(AcademicYear).where(AcademicYear.year_number == int(year_number))).scalar_one_or_none()
    if ay is None:
        raise HTTPException(status_code=404, detail="ACADEMIC_YEAR_NOT_FOUND")
    return ay


def _get_subject(db: Session, program_id: uuid.UUID, academic_year_id: uuid.UUID, subject_code: str) -> Subject:
    subject = (
        db.execute(
            select(Subject)
            .where(Subject.program_id == program_id)
            .where(Subject.academic_year_id == academic_year_id)
            .where(Subject.code == subject_code)
        )
        .scalars()
        .first()
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="SUBJECT_NOT_FOUND")
    return subject


@router.get("/track-subjects", response_model=list[TrackSubjectOut])
def list_track_subjects(
    program_code: str = Query(min_length=1),
    academic_year_number: int = Query(ge=1, le=4),
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[TrackSubjectOut]:
    program = _get_program(db, program_code)
    ay = _get_academic_year(db, int(academic_year_number))
    rows = (
        db.execute(
            select(TrackSubject)
            .where(TrackSubject.program_id == program.id)
            .where(TrackSubject.academic_year_id == ay.id)
            .order_by(TrackSubject.track.asc(), TrackSubject.created_at.asc())
        )
        .scalars()
        .all()
    )
    return rows


@router.post("/track-subjects", response_model=TrackSubjectOut)
def create_track_subject(
    payload: TrackSubjectCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> TrackSubjectOut:
    program = _get_program(db, payload.program_code)
    ay = _get_academic_year(db, int(payload.academic_year_number))
    subject = _get_subject(db, program.id, ay.id, payload.subject_code)

    row = TrackSubject(
        program_id=program.id,
        academic_year_id=ay.id,
        track=payload.track,
        subject_id=subject.id,
        is_elective=payload.is_elective,
        sessions_override=payload.sessions_override,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")
    db.refresh(row)
    return row


@router.patch("/track-subjects/{track_subject_id}", response_model=TrackSubjectOut)
def update_track_subject(
    track_subject_id: uuid.UUID,
    payload: TrackSubjectUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> TrackSubjectOut:
    row = db.get(TrackSubject, track_subject_id)
    if row is None:
        raise HTTPException(status_code=404, detail="TRACK_SUBJECT_NOT_FOUND")

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(row, k, v)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")
    db.refresh(row)
    return row


@router.delete("/track-subjects/{track_subject_id}")
def delete_track_subject(
    track_subject_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(TrackSubject, track_subject_id)
    if row is None:
        raise HTTPException(status_code=404, detail="TRACK_SUBJECT_NOT_FOUND")
    db.delete(row)
    db.commit()
    return {"ok": True}
