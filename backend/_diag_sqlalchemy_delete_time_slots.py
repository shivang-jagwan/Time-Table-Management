from __future__ import annotations

from sqlalchemy import delete

from core.database import SessionLocal
from models.time_slot import TimeSlot


def main() -> None:
    db = SessionLocal()
    try:
        try:
            db.execute(delete(TimeSlot))
            db.flush()
            print("delete(TimeSlot) executed (rolling back)")
        except Exception as exc:  # noqa: BLE001
            print("EXC_CLASS", type(exc).__module__ + "." + type(exc).__name__)
            print(str(exc))
        finally:
            db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
