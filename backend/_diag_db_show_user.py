from __future__ import annotations

import os

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    username = os.environ.get("USERNAME", "graphicerahill").strip().lower()

    sql = """
    select
      id,
      username,
      name,
      role::text as role,
      is_active,
      case when password_hash is null then null else length(password_hash) end as password_hash_len,
      created_at
    from users
    where lower(coalesce(username, '')) = :u
    limit 5
    """.strip()

    with ENGINE.connect() as conn:
        rows = conn.execute(text(sql), {"u": username}).mappings().all()

    print({"match_count": len(rows), "rows": [dict(r) for r in rows]})


if __name__ == "__main__":
    main()
