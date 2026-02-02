from __future__ import annotations

"""Create `users` table and seed the default production admin user.

Safe to run multiple times.

Default user:
- username: graphicerahill
- role: ADMIN
- password hash: bcrypt (no plaintext stored)

NOTE: You should change this password after first login.
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


DEFAULT_USERNAME = "graphicerahill"
DEFAULT_ROLE = "ADMIN"
# bcrypt hash for password 'Graphic@ERA123'
DEFAULT_PASSWORD_HASH = "$2b$12$jg/TOq7ggcc0bCBKWGViuOHFhUypQlkcZaAg/WG9Pq21GI.WMiPRK"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    args = parser.parse_args()

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
        return

    with ENGINE.begin() as conn:
        for s in statements:
            conn.execute(
                text(s),
                {
                    "username": DEFAULT_USERNAME,
                    "password_hash": DEFAULT_PASSWORD_HASH,
                    "role": DEFAULT_ROLE,
                },
            )

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
                    values (:username, :username, :password_hash, :role, true)
                    on conflict (username) do nothing
                    """.strip()
                ),
                {
                    "username": DEFAULT_USERNAME,
                    "password_hash": DEFAULT_PASSWORD_HASH,
                    "role": DEFAULT_ROLE,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    insert into users (username, password_hash, role, is_active)
                    values (:username, :password_hash, :role, true)
                    on conflict (username) do nothing
                    """.strip()
                ),
                {
                    "username": DEFAULT_USERNAME,
                    "password_hash": DEFAULT_PASSWORD_HASH,
                    "role": DEFAULT_ROLE,
                },
            )

    print("OK: ensured users table and seeded default admin user (if missing).")


if __name__ == "__main__":
    main()
