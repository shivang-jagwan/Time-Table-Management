from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from models.base import Base


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day_of_week = Column(Integer, nullable=False)
    slot_index = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("day_of_week >= 0 and day_of_week <= 5", name="ck_time_slots_day"),
        CheckConstraint("slot_index >= 0", name="ck_time_slots_slot_index"),
    )
