from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TrackSubjectBase(BaseModel):
    program_code: str = Field(min_length=1)
    academic_year_number: int = Field(ge=1, le=4)
    track: str = Field(min_length=1)
    subject_code: str = Field(min_length=1)
    is_elective: bool = False
    sessions_override: int | None = Field(default=None, ge=0)


class TrackSubjectCreate(TrackSubjectBase):
    pass


class TrackSubjectUpdate(BaseModel):
    track: str | None = None
    is_elective: bool | None = None
    sessions_override: int | None = Field(default=None, ge=0)


class TrackSubjectOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    academic_year_id: uuid.UUID
    track: str
    subject_id: uuid.UUID
    is_elective: bool
    sessions_override: int | None
    created_at: datetime

    class Config:
        from_attributes = True
