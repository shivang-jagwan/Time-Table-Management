from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import require_admin
from core.db import get_db
from models.program import Program
from schemas.program import ProgramCreate, ProgramOut, ProgramUpdate


router = APIRouter()


@router.get("/", response_model=list[ProgramOut])
def list_programs(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ProgramOut]:
    return db.execute(select(Program).order_by(Program.code.asc())).scalars().all()


@router.post("/", response_model=ProgramOut)
def create_program(
    payload: ProgramCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProgramOut:
    program = Program(**payload.model_dump())
    db.add(program)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="PROGRAM_CODE_ALREADY_EXISTS")
    db.refresh(program)
    return program


@router.patch("/{program_id}", response_model=ProgramOut)
def update_program(
    program_id: uuid.UUID,
    payload: ProgramUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> ProgramOut:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="PROGRAM_NOT_FOUND")

    updates = payload.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(program, k, v)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")

    db.refresh(program)
    return program


@router.delete("/{program_id}")
def delete_program(
    program_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    program = db.get(Program, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="PROGRAM_NOT_FOUND")
    db.delete(program)
    db.commit()
    return {"ok": True}
