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


def _user_exists_case_insensitive(conn, username: str) -> bool:
    row = conn.execute(
        text("select 1 from users where lower(username) = lower(:u) limit 1"),
        {"u": username},
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
        has_name = _has_name_column(conn)

        for username, password in ADMINS:
            if _user_exists_case_insensitive(conn, username):
                continue

            password_hash = hash_password(password)

            if has_name:
                conn.execute(
                    text(
                        """
                        insert into users (name, username, password_hash, role, is_active)
                        values (:name, :username, :password_hash, 'ADMIN', true)
                        on conflict (username) do nothing
                        """.strip()
                    ),
                    {
                        "name": username,
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

    print("OK: ensured 2 admin users exist (inserted if missing).")


if __name__ == "__main__":
    main()
