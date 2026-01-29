from __future__ import annotations

import os
from pathlib import Path

import psycopg2


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def main() -> int:
    backend_dir = Path(__file__).resolve().parent
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    conninfo = _normalize_psycopg_url(database_url)
    with psycopg2.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from section_time_windows")
            total = cur.fetchone()[0]
            cur.execute(
                """
                select count(*)
                from (
                  select section_id, day_of_week
                  from section_time_windows
                  group by section_id, day_of_week
                  having count(*) > 1
                ) t
                """
            )
            dup_groups = cur.fetchone()[0]

    print({"section_time_windows_total": total, "duplicate_section_day_groups": dup_groups})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
