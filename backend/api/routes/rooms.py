from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import require_admin
from core.db import get_db
from models.fixed_timetable_entry import FixedTimetableEntry
from models.room import Room
from models.timetable_entry import TimetableEntry
from schemas.room import RoomCreate, RoomOut, RoomUpdate


logger = logging.getLogger(__name__)


router = APIRouter()


def _ensure_unique_room_code(db: Session, *, code: str, exclude_room_id: uuid.UUID | None) -> None:
    q = select(Room.id).where(Room.code == code)
    if exclude_room_id is not None:
        q = q.where(Room.id != exclude_room_id)
    if db.execute(q.limit(1)).first() is not None:
        raise HTTPException(status_code=409, detail="ROOM_CODE_ALREADY_EXISTS")


@router.get("/", response_model=list[RoomOut])
def list_rooms(
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[RoomOut]:
    return db.execute(select(Room).order_by(Room.code.asc())).scalars().all()


@router.post("/", response_model=RoomOut)
def create_room(
    payload: RoomCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> RoomOut:
    data = payload.model_dump()
    data["code"] = str(data["code"]).strip()
    data["name"] = str(data["name"]).strip()
    if not data["code"]:
        raise HTTPException(status_code=400, detail="INVALID_CODE")
    if not data["name"]:
        raise HTTPException(status_code=400, detail="INVALID_NAME")

    _ensure_unique_room_code(db, code=data["code"], exclude_room_id=None)

    room = Room(**data)
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="ROOM_CODE_ALREADY_EXISTS")
    db.refresh(room)
    return room


@router.put("/{room_id}", response_model=RoomOut)
def put_room(
    room_id: uuid.UUID,
    payload: RoomCreate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> RoomOut:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")

    data = payload.model_dump()
    data["code"] = str(data["code"]).strip()
    data["name"] = str(data["name"]).strip()
    if not data["code"]:
        raise HTTPException(status_code=400, detail="INVALID_CODE")
    if not data["name"]:
        raise HTTPException(status_code=400, detail="INVALID_NAME")

    _ensure_unique_room_code(db, code=data["code"], exclude_room_id=room_id)

    if str(room.room_type) != str(data.get("room_type")):
        used_in_runs = db.execute(select(TimetableEntry.id).where(TimetableEntry.room_id == room_id).limit(1)).first()
        used_in_fixed = db.execute(
            select(FixedTimetableEntry.id).where(FixedTimetableEntry.room_id == room_id).limit(1)
        ).first()
        if used_in_runs or used_in_fixed:
            logger.warning(
                "Room type changed for room_id=%s (code=%s) but room is referenced by timetable/fixed entries",
                str(room_id),
                str(room.code),
            )

    room.code = data["code"]
    room.name = data["name"]
    room.room_type = data["room_type"]
    room.capacity = int(data["capacity"])
    room.is_active = bool(data["is_active"])

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="ROOM_CODE_ALREADY_EXISTS")
    db.refresh(room)
    return room


@router.patch("/{room_id}", response_model=RoomOut)
def update_room(
    room_id: uuid.UUID,
    payload: RoomUpdate,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> RoomOut:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")

    updates = payload.model_dump(exclude_unset=True)
    if "code" in updates and updates.get("code") is not None:
        updates["code"] = str(updates["code"]).strip()
        if not updates["code"]:
            raise HTTPException(status_code=400, detail="INVALID_CODE")
        _ensure_unique_room_code(db, code=str(updates["code"]), exclude_room_id=room_id)
    if "name" in updates and updates.get("name") is not None:
        updates["name"] = str(updates["name"]).strip()
        if not updates["name"]:
            raise HTTPException(status_code=400, detail="INVALID_NAME")

    if "room_type" in updates and updates.get("room_type") is not None and str(room.room_type) != str(updates["room_type"]):
        used_in_runs = db.execute(select(TimetableEntry.id).where(TimetableEntry.room_id == room_id).limit(1)).first()
        used_in_fixed = db.execute(
            select(FixedTimetableEntry.id).where(FixedTimetableEntry.room_id == room_id).limit(1)
        ).first()
        if used_in_runs or used_in_fixed:
            logger.warning(
                "Room type changed for room_id=%s (code=%s) but room is referenced by timetable/fixed entries",
                str(room_id),
                str(room.code),
            )
    for k, v in updates.items():
        setattr(room, k, v)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CONFLICT")
    db.refresh(room)
    return room


@router.delete("/{room_id}")
def delete_room(
    room_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="ROOM_NOT_FOUND")
    db.delete(room)
    db.commit()
    return {"ok": True}
