from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
            v = v[1:-1]
        os.environ.setdefault(k, v)


def main() -> None:
    load_env_file(Path(__file__).resolve().parent / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL missing")

    engine = create_engine(db_url, pool_pre_ping=True)
    tables = [
        "elective_blocks",
        "elective_block_subjects",
        "section_elective_blocks",
        "timetable_entries",
    ]

    with engine.connect() as conn:
        for table in tables:
            cols = conn.execute(
                text(
                    """
                    select column_name, data_type
                    from information_schema.columns
                    where table_schema='public' and table_name=:t
                    order by ordinal_position
                    """
                ),
                {"t": table},
            ).fetchall()
            print(f"{table} columns:")
            if not cols:
                print("  <missing>")
            else:
                for name, dtype in cols:
                    print(f"  - {name}: {dtype}")


if __name__ == "__main__":
    main()
