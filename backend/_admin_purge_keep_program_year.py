"""Dangerous admin utility: purge almost all data.

Keeps only:
- programs
- academic_years

Everything else in public schema is TRUNCATE'd with CASCADE.

Safety:
- Refuses to run against non-local hosts unless you pass --allow-remote
- Requires you to confirm host + database name via flags
- Requires --yes-really

Usage (PowerShell):
  D:/gpt/backend/.venv/Scripts/python.exe d:/gpt/backend/_admin_purge_keep_program_year.py --list

  D:/gpt/backend/.venv/Scripts/python.exe d:/gpt/backend/_admin_purge_keep_program_year.py \
    --confirm-host "localhost" --confirm-db "postgres" --yes-really

If DATABASE_URL points to Supabase or any remote host, you must also pass --allow-remote.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url

from core.config import settings
from core.database import ENGINE, is_transient_db_connectivity_error


KEEP_TABLES = {"programs", "academic_years"}


def _make_purge_engine():
    # Use a separate engine so we can safely bump connect_timeout without
    # changing the app's global engine.
    # IMPORTANT: use the original settings.database_url (env) rather than str(ENGINE.url)
    # so we preserve credential encoding exactly as configured.
    raw = settings.database_url.strip()
    if raw.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + raw.removeprefix("postgresql://")
    elif raw.startswith("postgres://"):
        url = "postgresql+psycopg2://" + raw.removeprefix("postgres://")
    elif raw.startswith("postgresql+psycopg://"):
        url = "postgresql+psycopg2://" + raw.removeprefix("postgresql+psycopg://")
    else:
        url = raw
    connect_args: dict[str, object] = {"connect_timeout": 20}

    # Preserve sslmode if present in URL query; otherwise rely on SQLAlchemy's URL.
    try:
        parsed = make_url(url)
        host = (parsed.host or "").lower()
        if host.endswith("supabase.com") and "sslmode" not in (parsed.query or {}):
            connect_args["sslmode"] = "require"
    except Exception:
        pass

    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


PURGE_ENGINE = _make_purge_engine()


def _run_with_retries(fn, *, attempts: int = 6) -> None:
    delays = [0.5, 1.0, 2.0, 3.0, 5.0]
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            fn()
            return
        except OperationalError as exc:
            last_exc = exc
            if not is_transient_db_connectivity_error(exc) or i >= attempts - 1:
                raise
            time.sleep(delays[min(i, len(delays) - 1)])
    if last_exc is not None:
        raise last_exc


@dataclass(frozen=True)
class DbTarget:
    host: str
    database: str
    username: str | None
    drivername: str


def _redact_url(u: str) -> str:
    try:
        url = make_url(u)
        # Avoid printing password.
        return str(url.set(password="***"))
    except Exception:
        return "<unparseable DATABASE_URL>"


def _get_target() -> DbTarget:
    url = PURGE_ENGINE.url
    return DbTarget(
        host=str(url.host or ""),
        database=str(url.database or ""),
        username=str(url.username) if url.username else None,
        drivername=str(url.drivername or ""),
    )


def _is_local_host(host: str) -> bool:
    h = (host or "").lower().strip()
    return h in {"localhost", "127.0.0.1", "::1"} or h.endswith(".local")


def _quote_ident(name: str) -> str:
    # Conservative quoting for Postgres identifiers.
    return '"' + name.replace('"', '""') + '"'


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge DB data, keeping only programs + academic_years")
    parser.add_argument("--list", action="store_true", help="List tables that would be truncated and exit")
    parser.add_argument("--allow-remote", action="store_true", help="Allow running against non-local DB hosts")
    parser.add_argument("--confirm-host", type=str, default="", help="Must match DATABASE_URL host")
    parser.add_argument("--confirm-db", type=str, default="", help="Must match DATABASE_URL database")
    parser.add_argument("--yes-really", action="store_true", help="Actually execute TRUNCATE")
    args = parser.parse_args()

    target = _get_target()

    # Print a safe-ish connection string.
    try:
        safe_url = _redact_url(str(PURGE_ENGINE.url))
    except Exception:
        safe_url = "<unknown>"

    print("DATABASE_URL:", safe_url)
    print("Target:", {"host": target.host, "db": target.database, "user": target.username, "driver": target.drivername})

    if not target.host or not target.database:
        raise SystemExit("Refusing to run: could not parse host/database from DATABASE_URL")

    if not args.allow_remote and not _is_local_host(target.host):
        raise SystemExit(
            f"Refusing to run on non-local host '{target.host}'. Re-run with --allow-remote if you are absolutely sure."
        )

    if args.confirm_host.strip() != target.host:
        raise SystemExit(f"Refusing to run: --confirm-host must equal '{target.host}'")

    if args.confirm_db.strip() != target.database:
        raise SystemExit(f"Refusing to run: --confirm-db must equal '{target.database}'")

    tables: list[str] = []

    def _fetch_tables() -> None:
        nonlocal tables
        with PURGE_ENGINE.connect() as conn:
            tables = (
                conn.execute(
                    text(
                        """
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                        ORDER BY tablename;
                        """
                    )
                )
                .scalars()
                .all()
            )

    _run_with_retries(_fetch_tables)

    to_truncate = [t for t in tables if t not in KEEP_TABLES]

    print("Keep tables:", sorted(KEEP_TABLES))
    print(f"Found {len(tables)} public tables; will truncate {len(to_truncate)}.")

    if args.list or not args.yes_really:
        for t in to_truncate:
            print("TRUNCATE:", t)
        if not args.yes_really:
            print("\nDry run only. Pass --yes-really to execute.")
        return 0

    if not to_truncate:
        print("Nothing to truncate.")
        return 0

    stmt = "TRUNCATE TABLE " + ", ".join(_quote_ident(t) for t in to_truncate) + " RESTART IDENTITY CASCADE;"

    def _truncate() -> None:
        with PURGE_ENGINE.begin() as conn:
            conn.execute(text(stmt))

    _run_with_retries(_truncate)

    print("Done. Truncated tables (kept programs + academic_years).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
