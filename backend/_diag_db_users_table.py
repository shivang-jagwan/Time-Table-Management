from __future__ import annotations

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    sql = """
    select column_name, data_type
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'users'
    order by ordinal_position
    """.strip()

    with ENGINE.connect() as conn:
        rows = conn.execute(text(sql)).all()

    print({"users_columns": [(r[0], r[1]) for r in rows]})


if __name__ == "__main__":
    main()
