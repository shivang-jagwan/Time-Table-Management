from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_tenant_id, require_admin
from api.tenant import get_by_id, where_tenant
from core.cache import cache_delete_prefix, cache_get_json, cache_set_json
from core.db import get_db
from models.program import Program
from models.timetable_run import TimetableRun
from schemas.program import ProgramCreate, ProgramOut, ProgramUpdate


router = APIRouter()


def _tenant_scope_key(tenant_id: uuid.UUID | None) -> str:
    return str(tenant_id) if tenant_id is not None else "shared"


@router.get("/latest")
def get_latest_program(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> dict:
    """Return the program_code of the most recently run timetable (any status)."""
    cache_key = f"programs:latest:{_tenant_scope_key(tenant_id)}"
    cached = cache_get_json(cache_key)
    if isinstance(cached, dict) and cached.get("program_code"):
        return {"program_code": str(cached["program_code"])}

    q = (
        where_tenant(select(TimetableRun), TimetableRun, tenant_id)
        .where(TimetableRun.parameters["program_code"].astext != None)  # noqa: E711
        .order_by(TimetableRun.created_at.desc())
        .limit(1)
    )
    run = db.execute(q).scalars().first()
    if run is not None:
        code = (run.parameters or {}).get("program_code")
        if code:
            payload = {"program_code": code}
            cache_set_json(cache_key, payload)
            return payload

    # Fallback: first program alphabetically
    q2 = where_tenant(select(Program), Program, tenant_id).order_by(Program.code.asc()).limit(1)
    prog = db.execute(q2).scalars().first()
    if prog is None:
        raise HTTPException(status_code=404, detail="NO_PROGRAMS")
    payload = {"program_code": prog.code}
    cache_set_json(cache_key, payload)
    return payload


@router.get("/", response_model=list[ProgramOut])
def list_programs(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> list[ProgramOut]:
    cache_key = f"programs:list:{_tenant_scope_key(tenant_id)}"
    cached = cache_get_json(cache_key)
    if isinstance(cached, list):
        return [ProgramOut.model_validate(item) for item in cached]

    q = where_tenant(select(Program), Program, tenant_id).order_by(Program.code.asc())
    rows = db.execute(q).scalars().all()
    payload = [ProgramOut.model_validate(r).model_dump(mode="json") for r in rows]
    cache_set_json(cache_key, payload)
    return rows


@router.post("/", response_model=ProgramOut)
def create_program(
    payload: ProgramCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> ProgramOut:
    data = payload.model_dump()
    if tenant_id is not None:
        data["tenant_id"] = tenant_id
    program = Program(**data)
    db.add(program)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()

        # If DB is in strict per-tenant mode (tenant_id NOT NULL) but the app is running
        # without a resolved tenant context, Postgres raises NOT NULL violation (23502).
        # Returning a duplicate-code error here is misleading.
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        msg = str(getattr(exc, "orig", exc) or "")
        if pgcode == "23502" or "null value in column \"tenant_id\"" in msg.lower():
            raise HTTPException(status_code=500, detail="TENANT_CONTEXT_MISSING")

        raise HTTPException(status_code=409, detail="PROGRAM_CODE_ALREADY_EXISTS")
    db.refresh(program)
    cache_delete_prefix(f"programs:{_tenant_scope_key(tenant_id)}")
    cache_delete_prefix("programs:list:")
    cache_delete_prefix("programs:latest:")
    return program


@router.patch("/{program_id}", response_model=ProgramOut)
def update_program(
    program_id: uuid.UUID,
    payload: ProgramUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> ProgramOut:
    program = get_by_id(db, Program, program_id, tenant_id)
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
    cache_delete_prefix(f"programs:{_tenant_scope_key(tenant_id)}")
    cache_delete_prefix("programs:list:")
    cache_delete_prefix("programs:latest:")
    return program


@router.delete("/{program_id}")
def delete_program(
    program_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID | None = Depends(get_tenant_id),
) -> dict:
    program = get_by_id(db, Program, program_id, tenant_id)
    if program is None:
        raise HTTPException(status_code=404, detail="PROGRAM_NOT_FOUND")
    db.delete(program)
    db.commit()
    cache_delete_prefix(f"programs:{_tenant_scope_key(tenant_id)}")
    cache_delete_prefix("programs:list:")
    cache_delete_prefix("programs:latest:")
    return {"ok": True}
