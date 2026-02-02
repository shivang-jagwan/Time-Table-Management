"""Verify purge results by reporting row counts for key tables.

Read-only: performs SELECT COUNT(*) queries.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from core.config import settings


def _normalize_db_url(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg2://" + raw.removeprefix("postgresql://")
    if raw.startswith("postgres://"):
        return "postgresql+psycopg2://" + raw.removeprefix("postgres://")
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg2://" + raw.removeprefix("postgresql+psycopg://")
    return raw


def main() -> None:
    url = _normalize_db_url(settings.database_url)
    engine = create_engine(url)

    tables = [
        "programs",
        "academic_years",
        "teachers",
        "rooms",
        "subjects",
        "sections",
        "time_slots",
        "timetable_entries",
        "special_allotments",
        "fixed_timetable_entries",
        "solver_runs",
    ]

    with engine.connect() as conn:
        existing = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_type='BASE TABLE'"
                )
            ).all()
        }

        for table in tables:
            if table not in existing:
                print(f"{table}: N/A (table missing)")
                continue

            count = conn.execute(
                text('SELECT COUNT(*) FROM public."' + table + '"')
            ).scalar_one()
            print(f"{table}: {count}")


if __name__ == "__main__":
    main()
