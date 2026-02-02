from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import psycopg2


CONFIRM_PHRASE = "DELETE_ALL_DATA"


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


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class TableRef:
    schema: str
    name: str

    def fqn_sql(self) -> str:
        return f"{_quote_ident(self.schema)}.{_quote_ident(self.name)}"


def _list_tables(cur, *, schema: str, exclude: set[str]) -> list[TableRef]:
    cur.execute(
        """
SELECT schemaname, tablename
FROM pg_catalog.pg_tables
WHERE schemaname = %s
ORDER BY tablename;
""",
        (schema,),
    )
    rows = cur.fetchall() or []
    tables: list[TableRef] = []
    for schemaname, tablename in rows:
        if tablename in exclude:
            continue
        tables.append(TableRef(schema=schemaname, name=tablename))
    return tables


def _count_rows(cur, table: TableRef) -> int:
    cur.execute(f"SELECT count(*) FROM {table.fqn_sql()};")
    return int(cur.fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DEV ONLY: Delete ALL data from the database by truncating every table in the schema. "
            "This will remove teachers/subjects/sections/runs/locks/time-slots/etc."
        )
    )
    parser.add_argument(
        "--schema",
        type=str,
        default="public",
        help="Schema to wipe (default: public)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Table name to exclude (can be repeated). Example: --exclude time_slots",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually perform deletions. Without this, the script only prints counts.",
    )
    parser.add_argument(
        "--confirm",
        type=str,
        default=None,
        help=f"Must be exactly {CONFIRM_PHRASE!r} to run with --yes.",
    )

    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    exclude = set(args.exclude)
    conninfo = _normalize_psycopg_url(database_url)

    with psycopg2.connect(conninfo) as conn:
        with conn.cursor() as cur:
            tables = _list_tables(cur, schema=args.schema, exclude=exclude)
            if not tables:
                print(f"No tables found in schema {args.schema!r} (after excludes).")
                return 0

            print(f"Schema: {args.schema}")
            print("Tables to be truncated:")
            for t in tables:
                print(f"- {t.name}")

            total_rows = 0
            print("\nRow counts:")
            for t in tables:
                cnt = _count_rows(cur, t)
                total_rows += cnt
                print(f"- {t.name}: {cnt}")

            if not args.yes:
                print("\nDry run only. Re-run with --yes --confirm DELETE_ALL_DATA to truncate.")
                return 0

            if args.confirm != CONFIRM_PHRASE:
                raise SystemExit(f"Refusing to delete. Pass --confirm {CONFIRM_PHRASE!r} to proceed.")

            # TRUNCATE with CASCADE handles FK dependencies.
            fqn_list = ", ".join(t.fqn_sql() for t in tables)
            cur.execute(f"TRUNCATE TABLE {fqn_list} RESTART IDENTITY CASCADE;")

            print(f"\nOK: truncated {len(tables)} tables; previous total rows: {total_rows}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
