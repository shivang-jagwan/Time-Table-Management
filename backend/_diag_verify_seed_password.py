from __future__ import annotations

import os

from sqlalchemy import text

from core.database import ENGINE
from core.security import verify_password


def main() -> None:
    username = os.environ.get("AUTH_USERNAME", "graphicerahill").strip().lower()
    password = os.environ.get("AUTH_PASSWORD", "Graphic@ERA123")

    with ENGINE.connect() as conn:
        row = conn.execute(
            text("select username, password_hash from users where lower(username)=:u limit 1"),
            {"u": username},
        ).first()

        if not row:
            existing = conn.execute(text("select username from users")).scalars().all()
            print({"found": False, "searched": username, "existing_usernames": existing})
            return

    _u, password_hash = row
    ok = verify_password(password, str(password_hash))
    print({"found": True, "username": _u, "password_ok": bool(ok)})


if __name__ == "__main__":
    main()
