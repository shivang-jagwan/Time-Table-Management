from __future__ import annotations

import argparse
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
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a SQL file against Postgres using DATABASE_URL")
    parser.add_argument("sql_file", type=str, help="Path to .sql file")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    sql_path = Path(args.sql_file).resolve()
    sql = sql_path.read_text(encoding="utf-8")

    conninfo = _normalize_psycopg_url(database_url)
    with psycopg2.connect(conninfo) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql)

    print(f"OK: executed {sql_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
