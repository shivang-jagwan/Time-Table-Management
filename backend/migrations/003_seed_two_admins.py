from __future__ import annotations

"""Seed two admin users.

Safe to run multiple times.

Run:
  python -m migrations.003_seed_two_admins --yes

Or:
  python backend/migrations/003_seed_two_admins.py --yes

IMPORTANT:
- This seeds specific credentials provided by the project owner.
- Change these passwords after first login.
"""

import argparse
import sys
from pathlib import Path

# Allow running this script from any working directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from core.database import ENGINE
from core.security import hash_password


ADMINS: list[tuple[str, str]] = [
    ("DeepaliDon", "Deepalidon@always"),
    ("chotapaaji", "chotasardar"),
]


DEFAULT_TENANT_SLUG = "default"


def _ensure_users_schema(conn) -> None:
    # Keep this idempotent: safe across reruns.
    # This script is tenant-aware and compatible with strict per-tenant mode.
    statements = [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
        """
        CREATE TABLE IF NOT EXISTS tenants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT now()
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                username VARCHAR(100) NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(20) DEFAULT 'ADMIN',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT now()
        );
        """,
        # Legacy compatibility: older DBs may have public.users with missing columns.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id UUID;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
        # Backfill username from legacy `name` if present.
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users' AND column_name='name'
            ) THEN
                EXECUTE 'UPDATE users SET username = COALESCE(username, name::text) WHERE username IS NULL';
            END IF;
        END $$;
        """,
        # Per-tenant case-insensitive uniqueness (no citext dependency).
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_tenant_username_ci ON users (tenant_id, lower(username));",
    ]

    for s in statements:
        conn.execute(text(s))


def _ensure_default_tenant(conn) -> str:
    row = conn.execute(
        text("select id from tenants where lower(slug) = lower(:s) limit 1"),
        {"s": DEFAULT_TENANT_SLUG},
    ).first()
    if row is not None:
        return str(row[0])

    row2 = conn.execute(
        text("insert into tenants (slug, name) values (:slug, :name) returning id"),
        {"slug": DEFAULT_TENANT_SLUG, "name": "Default College"},
    ).first()
    if row2 is None:
        raise SystemExit("Failed to create default tenant")
    return str(row2[0])


def _has_name_column(conn) -> bool:
    return (
        conn.execute(
            text(
                """
                select 1
                from information_schema.columns
                where table_schema='public'
                  and table_name='users'
                  and column_name='name'
                limit 1
                """.strip()
            )
        ).first()
        is not None
    )


def _user_exists_case_insensitive(conn, *, tenant_id: str, username: str) -> bool:
    row = conn.execute(
        text("select 1 from users where tenant_id = :t and lower(username) = lower(:u) limit 1"),
        {"t": tenant_id, "u": username},
    ).first()
    return row is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    args = parser.parse_args()

    if not args.yes:
        print("Dry run. Re-run with --yes to apply.")
        for username, _password in ADMINS:
            print(f"Would ensure admin user exists: {username!r}")
        return

    with ENGINE.begin() as conn:
        _ensure_users_schema(conn)
        tenant_id = _ensure_default_tenant(conn)
        has_name = _has_name_column(conn)

        for username, password in ADMINS:
            if _user_exists_case_insensitive(conn, tenant_id=tenant_id, username=username):
                continue

            password_hash = hash_password(password)

            if has_name:
                conn.execute(
                    text(
                        """
                        insert into users (tenant_id, name, username, password_hash, role, is_active)
                        values (:tenant_id, :name, :username, :password_hash, 'ADMIN', true)
                        on conflict do nothing
                        """.strip()
                    ),
                    {
                        "tenant_id": tenant_id,
                        "name": username,
                        "username": username,
                        "password_hash": password_hash,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        insert into users (tenant_id, username, password_hash, role, is_active)
                        values (:tenant_id, :username, :password_hash, 'ADMIN', true)
                        on conflict do nothing
                        """.strip()
                    ),
                    {
                        "tenant_id": tenant_id,
                        "username": username,
                        "password_hash": password_hash,
                    },
                )

    print("OK: ensured 2 admin users exist (inserted if missing).")


if __name__ == "__main__":
    main()
