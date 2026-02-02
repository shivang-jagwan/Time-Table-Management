from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this script from any working directory.
BACKEND_DIR = Path(__file__).resolve().parents[0]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    parser = argparse.ArgumentParser(description="Set a user's role (ADMIN/USER) by username.")
    parser.add_argument("username", help="Username to update")
    parser.add_argument("--role", default="ADMIN", help="ADMIN or USER (default: ADMIN)")
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    args = parser.parse_args()

    username = args.username.strip()
    role = args.role.strip().upper()
    if role not in {"ADMIN", "USER"}:
        raise SystemExit("Invalid --role. Use ADMIN or USER.")

    if not username:
        raise SystemExit("Username is required")

    if not args.yes:
        print("Dry run. Re-run with --yes to apply.")
        print(f"Would set role={role} for username={username!r}")
        return

    with ENGINE.begin() as conn:
        # Update case-insensitively.
        res = conn.execute(
            text(
                """
                update users
                set role = :role
                where lower(username) = lower(:username)
                returning id, username, role, is_active
                """.strip()
            ),
            {"username": username, "role": role},
        ).first()

        if res is None:
            raise SystemExit(f"No such user: {username!r}")

        print({"id": str(res[0]), "username": res[1], "role": res[2], "is_active": bool(res[3])})


if __name__ == "__main__":
    main()
