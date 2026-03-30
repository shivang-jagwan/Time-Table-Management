#!/usr/bin/env python3
"""Hard-delete all data for a username by tenant scope.

Deletes every row with tenant_id matching the user's tenant across all public tables,
then deletes users and tenant row itself.

Usage:
  python _admin_delete_all_data_for_user.py --username shivang123
  python _admin_delete_all_data_for_user.py --username shivang123 --yes-really
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True, help="Username whose tenant data will be deleted")
    parser.add_argument("--yes-really", action="store_true", help="Actually execute deletion")
    return parser.parse_args()


def _fetch_one(db, sql: str, params: dict[str, Any] | None = None):
    return db.execute(text(sql), params or {}).first()


def _fetch_all(db, sql: str, params: dict[str, Any] | None = None):
    return db.execute(text(sql), params or {}).all()


def main() -> int:
    args = _parse_args()
    db = SessionLocal()

    try:
        user_row = _fetch_one(
            db,
            """
            SELECT id, username, tenant_id
            FROM users
            WHERE lower(username) = lower(:u)
            LIMIT 1
            """,
            {"u": args.username},
        )
        if not user_row:
            print(f"[ERROR] user not found: {args.username}")
            return 1

        user_id, username, tenant_id = user_row
        print(f"user_id={user_id}")
        print(f"username={username}")
        print(f"tenant_id={tenant_id}")

        # Discover all public base tables that carry tenant_id.
        tenant_tables_rows = _fetch_all(
            db,
            """
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema
             AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name = 'tenant_id'
            ORDER BY c.table_name
            """,
        )
        tenant_tables = [r[0] for r in tenant_tables_rows]

        # Preferred dependency-aware order (children first), then any remaining tables.
        preferred = [
            "timetable_entries",
            "timetable_conflicts",
            "timetable_runs",
            "fixed_timetable_entries",
            "special_allotments",
            "combined_group_sections",
            "combined_groups",
            "section_elective_blocks",
            "elective_block_subjects",
            "elective_blocks",
            "teacher_subject_sections",
            "section_subjects",
            "section_time_windows",
            "teacher_time_windows",
            "subject_allowed_rooms",
            "curriculum_subjects",
            "track_subjects",
            "sections",
            "subjects",
            "teachers",
            "rooms",
            "time_slots",
            "academic_years",
            "programs",
            "users",
            "tenants",
        ]
        in_preferred = [t for t in preferred if t in tenant_tables]
        remaining = [t for t in tenant_tables if t not in in_preferred]
        delete_order = in_preferred + remaining

        # Current counts snapshot.
        per_table_count: dict[str, int] = {}
        total_rows = 0
        for table in delete_order:
            row = _fetch_one(
                db,
                f"SELECT COUNT(*) FROM public.\"{table}\" WHERE tenant_id = :tid",
                {"tid": str(tenant_id)},
            )
            cnt = int(row[0] if row else 0)
            per_table_count[table] = cnt
            total_rows += cnt

        print("\n=== PREVIEW (rows with this tenant_id) ===")
        for table, cnt in per_table_count.items():
            if cnt > 0:
                print(f"{table}: {cnt}")
        print(f"TOTAL_TENANT_ROWS={total_rows}")

        if not args.yes_really:
            print("\n[DRY RUN] No deletion executed. Re-run with --yes-really")
            return 0

        deleted_counts: dict[str, int] = defaultdict(int)

        # Multi-pass delete helps when there are unexpected FK relationships among tenant tables.
        for _pass in range(1, 6):
            progress = 0
            for table in delete_order:
                if table == "tenants":
                    continue
                try:
                    result = db.execute(
                        text(f"DELETE FROM public.\"{table}\" WHERE tenant_id = :tid"),
                        {"tid": str(tenant_id)},
                    )
                    rc = int(result.rowcount or 0)
                    if rc:
                        deleted_counts[table] += rc
                        progress += rc
                except Exception:
                    db.rollback()
                    # Continue pass; some tables may become deletable later in the pass.
                    continue

            if progress == 0:
                break
            db.commit()

        # Ensure target username row is gone even if shared edge-cases exist.
        user_del = db.execute(
            text("DELETE FROM public.users WHERE lower(username)=lower(:u) OR tenant_id = :tid"),
            {"u": str(username), "tid": str(tenant_id)},
        )
        deleted_counts["users"] += int(user_del.rowcount or 0)

        tenant_del = db.execute(
            text("DELETE FROM public.tenants WHERE id = :tid"),
            {"tid": str(tenant_id)},
        )
        deleted_counts["tenants"] += int(tenant_del.rowcount or 0)

        db.commit()

        # Verification.
        remaining_rows = 0
        remaining_by_table: dict[str, int] = {}
        for table in delete_order:
            row = _fetch_one(
                db,
                f"SELECT COUNT(*) FROM public.\"{table}\" WHERE tenant_id = :tid",
                {"tid": str(tenant_id)},
            )
            cnt = int(row[0] if row else 0)
            if cnt > 0:
                remaining_by_table[table] = cnt
                remaining_rows += cnt

        user_left = _fetch_one(
            db,
            "SELECT COUNT(*) FROM public.users WHERE lower(username)=lower(:u)",
            {"u": str(username)},
        )
        user_left_count = int(user_left[0] if user_left else 0)

        tenant_left = _fetch_one(
            db,
            "SELECT COUNT(*) FROM public.tenants WHERE id = :tid",
            {"tid": str(tenant_id)},
        )
        tenant_left_count = int(tenant_left[0] if tenant_left else 0)

        print("\n=== DELETION SUMMARY ===")
        for table in delete_order:
            cnt = int(deleted_counts.get(table, 0))
            if cnt > 0:
                print(f"deleted {table}: {cnt}")

        print("\n=== VERIFY ===")
        print(f"remaining_rows_with_tenant_id={remaining_rows}")
        print(f"remaining_user_by_username={user_left_count}")
        print(f"remaining_tenant_row={tenant_left_count}")

        if remaining_by_table:
            print("remaining_by_table:")
            for table, cnt in remaining_by_table.items():
                print(f"  {table}: {cnt}")

        if remaining_rows == 0 and user_left_count == 0 and tenant_left_count == 0:
            print("[OK] Hard delete complete")
            return 0

        print("[WARN] Some rows remain; review remaining_by_table above")
        return 2

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
