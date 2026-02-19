from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Allow running this script from any working directory.
BACKEND_DIR = Path(__file__).resolve().parents[0]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from core.database import ENGINE
from core.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a user's password by username (idempotent update).")
    parser.add_argument("username", help="Username to update")
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    args = parser.parse_args()

    username = (args.username or "").strip()
    if not username:
        raise SystemExit("Username is required")

    if not args.yes:
        print("Dry run. Re-run with --yes to apply.")
        print(f"Would set password for username={username!r}")
        return

    pw1 = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        raise SystemExit("Passwords do not match")
    if not pw1:
        raise SystemExit("Password cannot be empty")

    pw_hash = hash_password(pw1)

    with ENGINE.begin() as conn:
        res = conn.execute(
            text(
                """
                update users
                set password_hash = :pw
                where lower(username) = lower(:username)
                returning id, username, role, is_active
                """.strip()
            ),
            {"username": username, "pw": pw_hash},
        ).first()

    if res is None:
        raise SystemExit(f"No such user: {username!r}")

    print({"id": str(res[0]), "username": res[1], "role": res[2], "is_active": bool(res[3])})


if __name__ == "__main__":
    main()
