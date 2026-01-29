from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class SectionTimeWindowItem(BaseModel):
    day_of_week: int = Field(ge=0, le=5)
    start_slot_index: int = Field(ge=0)
    end_slot_index: int = Field(ge=0)


class PutSectionTimeWindowsRequest(BaseModel):
    windows: list[SectionTimeWindowItem] = Field(default_factory=list)


class SectionTimeWindowOut(SectionTimeWindowItem):
    id: UUID
    section_id: UUID
    created_at: str


class ListSectionTimeWindowsResponse(BaseModel):
    section_id: UUID
    windows: list[SectionTimeWindowOut]
