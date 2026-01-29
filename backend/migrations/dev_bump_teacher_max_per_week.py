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
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def main() -> int:
    """Dev helper.

    Raises teacher.max_per_week so academic-year validation/solve can run in a
    partially-migrated dev DB.

    Controlled by env var TEACHER_MAX_PER_WEEK (default 60).
    """

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    target_max = int(os.environ.get("TEACHER_MAX_PER_WEEK", "60"))

    conninfo = _normalize_psycopg_url(database_url)

    sql = """
    update teachers
    set max_per_week = greatest(max_per_week, %s)
    where max_per_week is not null;
    """

    with psycopg2.connect(conninfo) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("select count(*) from teachers")
            teachers_total = int(cur.fetchone()[0])
            cur.execute(sql, (target_max,))

    print({"teachers_total": teachers_total, "target_max_per_week": target_max})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
