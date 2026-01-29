from __future__ import annotations

import uuid

from pydantic import BaseModel


class SectionSubjectCreate(BaseModel):
    subject_id: uuid.UUID
