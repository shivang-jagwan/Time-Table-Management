from __future__ import annotations

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    sql = """
    select
      id,
      username,
      name,
      role::text as role,
      is_active,
      (password_hash is not null) as has_password_hash,
      case when password_hash is null then null else left(password_hash, 7) end as hash_prefix
    from users
    """.strip()

    with ENGINE.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()

    print([dict(r) for r in rows])


if __name__ == "__main__":
    main()
