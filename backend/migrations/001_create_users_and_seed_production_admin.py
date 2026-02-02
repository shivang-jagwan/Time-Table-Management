from __future__ import annotations

"""Create `users` table and (optionally) seed an initial production admin user.

Safe to run multiple times.

IMPORTANT SECURITY NOTE:
This script does NOT ship with any default admin credentials. Provide them explicitly
via flags or environment variables.
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running this script from any working directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from core.database import ENGINE
from core.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    parser.add_argument(
        "--username",
        default=None,
        help="Admin username (or set SEED_ADMIN_USERNAME env var)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Admin password (or set SEED_ADMIN_PASSWORD env var)",
    )
    args = parser.parse_args()

    username = (args.username or "").strip() or None
    if username is None:
        username = (
            (os.environ.get("SEED_ADMIN_USERNAME") or os.environ.get("ADMIN_SEED_USERNAME") or "").strip()
            or None
        )

    password = args.password if args.password not in {None, ""} else None
    if password is None:
        password = os.environ.get("SEED_ADMIN_PASSWORD") or os.environ.get("ADMIN_SEED_PASSWORD")

    password_hash = hash_password(password) if username and password else None

    statements = [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
        # Fresh install path.
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) DEFAULT 'ADMIN',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT now()
        );
        """,
        # Legacy compatibility: some existing DBs may already have a public.users table
        # with columns (id, name, role, created_at). Add the missing columns.
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
        # Ensure we have a unique index for ON CONFLICT.
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username);",
    ]

    if not args.yes:
        print("Dry run. Re-run with --yes to apply.")
        for s in statements:
            print("---")
            print(s.strip())
        if username and password:
            print("---")
            print(f"Would seed admin user: {username!r}")
        else:
            print("---")
            print("No admin seeding requested (provide --username + --password or env vars).")
        return

    with ENGINE.begin() as conn:
        for s in statements:
            conn.execute(
                text(s),
                {},
            )

        if username and password_hash:
            # Seed default admin. Some legacy schemas have a NOT NULL `name` column.
            has_name = (
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
            if has_name:
                conn.execute(
                    text(
                        """
                        insert into users (name, username, password_hash, role, is_active)
                        values (:username, :username, :password_hash, 'ADMIN', true)
                        on conflict (username) do nothing
                        """.strip()
                    ),
                    {
                        "username": username,
                        "password_hash": password_hash,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        insert into users (username, password_hash, role, is_active)
                        values (:username, :password_hash, 'ADMIN', true)
                        on conflict (username) do nothing
                        """.strip()
                    ),
                    {
                        "username": username,
                        "password_hash": password_hash,
                    },
                )

    if username and password_hash:
        print("OK: ensured users table and seeded admin user (if missing).")
    else:
        print("OK: ensured users table (no admin seeding requested).")


if __name__ == "__main__":
    main()
