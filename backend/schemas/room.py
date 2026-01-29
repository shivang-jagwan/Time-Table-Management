from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RoomBase(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    room_type: str = Field(min_length=1)
    capacity: int = Field(default=0, ge=0)
    is_active: bool = True


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    room_type: str | None = None
    capacity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class RoomOut(RoomBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True
