from __future__ import annotations

import psycopg2

from core.config import settings


def main() -> None:
    dsn = settings.database_url
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute("select count(*) from time_slots")
    print("time_slots", cur.fetchone()[0])

    cur.execute("select count(*) from timetable_entries")
    print("timetable_entries", cur.fetchone()[0])

    try:
        cur.execute("delete from time_slots")
        print("delete time_slots OK (rolling back)")
    except Exception as exc:  # noqa: BLE001
        print("delete time_slots ERROR", type(exc).__name__)
        print(str(exc))

    conn.rollback()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
