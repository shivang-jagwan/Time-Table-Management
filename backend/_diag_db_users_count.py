from __future__ import annotations

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    with ENGINE.connect() as conn:
        total = conn.execute(text("select count(*) from users")).scalar_one()
    print({"users_total": int(total)})


if __name__ == "__main__":
    main()
