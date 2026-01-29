from __future__ import annotations

from sqlalchemy import text

from core.database import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        row = db.execute(text("select 1 from timetable_entries limit 1")).first()
        print("row", row)
    finally:
        db.close()


if __name__ == "__main__":
    main()
