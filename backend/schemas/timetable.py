from __future__ import annotations

from pydantic import BaseModel


class TimetableGridEntryOut(BaseModel):
    day: int
    slot_index: int
    start_time: str
    end_time: str

    section_code: str
    subject_code: str
    teacher_name: str
    room_code: str
    year_number: int

    elective_block_id: str | None = None
    elective_block_name: str | None = None
