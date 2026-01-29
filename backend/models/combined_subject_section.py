from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.base import Base


class CombinedSubjectSection(Base):
    __tablename__ = "combined_subject_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    combined_group_id = Column(UUID(as_uuid=True), nullable=False)
    section_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
