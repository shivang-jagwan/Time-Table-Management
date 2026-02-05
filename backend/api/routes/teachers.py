from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_tenant_id, require_admin
from api.tenant import get_by_id, where_tenant
from core.db import get_db
from models.teacher import Teacher
from schemas.teacher import TeacherCreate, TeacherOut, TeacherPut, TeacherUpdate


router = APIRouter()


def _validate_teacher_constraints(
    *,
    weekly_off_day: int | None,
    max_per_day: int,
    max_per_week: int,
    max_continuous: int,
) -> None:
    errors: list[str] = []

    if weekly_off_day is not None and not (0 <= int(weekly_off_day) <= 5):
        errors.append("WEEKLY_OFF_DAY_OUT_OF_RANGE")
    if int(max_per_day) > 6:
        errors.append("MAX_PER_DAY_EXCEEDS_6")
    if int(max_per_week) > 36:
        errors.append("MAX_PER_WEEK_EXCEEDS_36")
    if int(max_per_day) > int(max_per_week):
        errors.append("MAX_PER_DAY_GT_MAX_PER_WEEK")
    if int(max_continuous) > int(max_per_day):
        errors.append("MAX_CONTINUOUS_GT_MAX_PER_DAY")
    if int(max_per_day) * 6 < int(max_per_week):
        errors.append("MAX_PER_DAY_TOO_LOW_FOR_WEEK")

    if errors:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_TEACHER_CONSTRAINTS",
                "errors": errors,
            },
        )


@router.get("/", response_model=list[TeacherOut])
def list_teachers(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> list[TeacherOut]:
    q = where_tenant(select(Teacher), Teacher, tenant_id).order_by(Teacher.full_name.asc())
    rows = db.execute(q).scalars().all()
    return rows


@router.post("/", response_model=TeacherOut)
def create_teacher(
    payload: TeacherCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> TeacherOut:
    _validate_teacher_constraints(
        weekly_off_day=payload.weekly_off_day,
        max_per_day=int(payload.max_per_day),
        max_per_week=int(payload.max_per_week),
        max_continuous=int(payload.max_continuous),
    )

    data = payload.model_dump()
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    teacher = Teacher(**data)
    db.add(teacher)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="TEACHER_CODE_ALREADY_EXISTS")
    db.refresh(teacher)
    return teacher


@router.patch("/{teacher_id}", response_model=TeacherOut)
def update_teacher(
    teacher_id: uuid.UUID,
    payload: TeacherUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> TeacherOut:
    teacher = get_by_id(db, Teacher, teacher_id, tenant_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="TEACHER_NOT_FOUND")

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(teacher, k, v)

    if {
        "weekly_off_day",
        "max_per_day",
        "max_per_week",
        "max_continuous",
    }.intersection(updates.keys()):
        _validate_teacher_constraints(
            weekly_off_day=teacher.weekly_off_day,
            max_per_day=int(teacher.max_per_day),
            max_per_week=int(teacher.max_per_week),
            max_continuous=int(teacher.max_continuous),
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")
    db.refresh(teacher)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherOut)
def put_teacher(
    teacher_id: uuid.UUID,
    payload: TeacherPut,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> TeacherOut:
    teacher = get_by_id(db, Teacher, teacher_id, tenant_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="TEACHER_NOT_FOUND")

    _validate_teacher_constraints(
        weekly_off_day=payload.weekly_off_day,
        max_per_day=int(payload.max_per_day),
        max_per_week=int(payload.max_per_week),
        max_continuous=int(payload.max_continuous),
    )

    teacher.full_name = payload.full_name
    teacher.weekly_off_day = payload.weekly_off_day
    teacher.max_per_day = int(payload.max_per_day)
    teacher.max_per_week = int(payload.max_per_week)
    teacher.max_continuous = int(payload.max_continuous)
    teacher.is_active = bool(payload.is_active)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")

    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}")
def delete_teacher(
    teacher_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> dict:
    teacher = get_by_id(db, Teacher, teacher_id, tenant_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="TEACHER_NOT_FOUND")
    db.delete(teacher)
    db.commit()
    return {"ok": True}
