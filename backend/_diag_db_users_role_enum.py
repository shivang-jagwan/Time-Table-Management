from __future__ import annotations

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    with ENGINE.connect() as conn:
        udt = conn.execute(
            text(
                """
                select udt_name
                from information_schema.columns
                where table_schema='public'
                  and table_name='users'
                  and column_name='role'
                """.strip()
            )
        ).scalar_one_or_none()

        if not udt:
            print({"role_type": None, "enum_values": None})
            return

        # If it's an enum, list values.
        values = conn.execute(
            text(
                """
                select e.enumlabel
                from pg_type t
                join pg_enum e on e.enumtypid = t.oid
                where t.typname = :typ
                order by e.enumsortorder
                """.strip()
            ),
            {"typ": udt},
        ).scalars().all()

    print({"role_udt_name": udt, "enum_values": values})


if __name__ == "__main__":
    main()
