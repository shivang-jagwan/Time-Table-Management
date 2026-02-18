from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def _fetch_one(cur, sql: str, params: tuple) -> object | None:
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return row[0]


def _print_counts(cur, *, year_number: int, program_code: str | None) -> None:
    params = {
        "year_number": year_number,
        "program_code": program_code,
    }

    cur.execute("select to_regclass('public.section_electives')")
    has_section_electives = cur.fetchone()[0] is not None

    counts_sql = """
WITH
  year AS (
    SELECT id FROM academic_years WHERE year_number = %(year_number)s
  ),
  program AS (
    SELECT id AS program_id FROM programs WHERE code = %(program_code)s
  ),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  ),
  blocks_y AS (
    SELECT b.id
    FROM elective_blocks b
    JOIN year y ON y.id = b.academic_year_id
    WHERE (%(program_code)s IS NULL OR b.program_id = (SELECT program_id FROM program))
  ),
  groups_y AS (
    SELECT g.id
    FROM combined_subject_groups g
    JOIN year y ON y.id = g.academic_year_id
    WHERE g.subject_id IN (SELECT id FROM subjects_y)
  ),
  groups2_y AS (
    SELECT g.id
    FROM combined_groups g
    JOIN year y ON y.id = g.academic_year_id
    WHERE g.subject_id IN (SELECT id FROM subjects_y)
  )
SELECT
  (SELECT count(*) FROM sections_y) AS sections,
  (SELECT count(*) FROM subjects_y) AS subjects,
  (SELECT count(*) FROM section_subjects WHERE section_id IN (SELECT id FROM sections_y) OR subject_id IN (SELECT id FROM subjects_y)) AS section_subjects,
  (SELECT count(*) FROM section_time_windows WHERE section_id IN (SELECT id FROM sections_y)) AS section_time_windows,
  """ + (
        "(SELECT count(*) FROM section_electives WHERE section_id IN (SELECT id FROM sections_y) OR subject_id IN (SELECT id FROM subjects_y)) AS section_electives,"
        if has_section_electives
        else "0 AS section_electives,"
    ) + """
  (SELECT count(*) FROM section_elective_blocks WHERE section_id IN (SELECT id FROM sections_y) OR block_id IN (SELECT id FROM blocks_y)) AS section_elective_blocks,
  (SELECT count(*) FROM track_subjects WHERE academic_year_id = (SELECT id FROM year) AND (%(program_code)s IS NULL OR program_id = (SELECT program_id FROM program))) AS track_subjects,
  (SELECT count(*) FROM teacher_subject_years WHERE academic_year_id = (SELECT id FROM year) AND subject_id IN (SELECT id FROM subjects_y)) AS teacher_subject_years,
  (SELECT count(*) FROM teacher_subject_sections WHERE section_id IN (SELECT id FROM sections_y) OR subject_id IN (SELECT id FROM subjects_y)) AS teacher_subject_sections,
  (SELECT count(*) FROM teacher_subjects WHERE subject_id IN (SELECT id FROM subjects_y)) AS teacher_subjects,
  (SELECT count(*) FROM elective_blocks WHERE id IN (SELECT id FROM blocks_y)) AS elective_blocks,
  (SELECT count(*) FROM elective_block_subjects WHERE block_id IN (SELECT id FROM blocks_y) OR subject_id IN (SELECT id FROM subjects_y)) AS elective_block_subjects,
  (SELECT count(*) FROM combined_groups WHERE id IN (SELECT id FROM groups2_y)) AS combined_groups,
  (SELECT count(*) FROM combined_group_sections WHERE combined_group_id IN (SELECT id FROM groups2_y) OR section_id IN (SELECT id FROM sections_y)) AS combined_group_sections,
  (SELECT count(*) FROM combined_subject_groups WHERE id IN (SELECT id FROM groups_y)) AS combined_subject_groups,
  (SELECT count(*) FROM combined_subject_sections WHERE combined_group_id IN (SELECT id FROM groups_y) OR section_id IN (SELECT id FROM sections_y)) AS combined_subject_sections,
  (SELECT count(*) FROM fixed_timetable_entries WHERE section_id IN (SELECT id FROM sections_y)) AS fixed_timetable_entries,
  (SELECT count(*) FROM special_allotments WHERE section_id IN (SELECT id FROM sections_y)) AS special_allotments,
  (SELECT count(*) FROM section_breaks WHERE section_id IN (SELECT id FROM sections_y)) AS section_breaks,
  (SELECT count(*) FROM timetable_entries WHERE section_id IN (SELECT id FROM sections_y)) AS timetable_entries,
  (SELECT count(*) FROM timetable_conflicts WHERE section_id IN (SELECT id FROM sections_y) OR subject_id IN (SELECT id FROM subjects_y)) AS timetable_conflicts
;
"""

    cur.execute(counts_sql, params)
    row = cur.fetchone()
    if not row:
        print("No rows returned.")
        return

    columns = [desc[0] for desc in cur.description]
    print("Counts to be deleted:")
    for col, val in zip(columns, row):
        print(f"- {col}: {val}")


def _delete_year_data(
    cur,
    *,
    year_number: int,
    program_code: str | None,
    delete_empty_runs: bool,
) -> dict[str, int]:
    params = {
        "year_number": year_number,
        "program_code": program_code,
    }

    cur.execute("select to_regclass('public.section_electives')")
    has_section_electives = cur.fetchone()[0] is not None

    deletes: list[tuple[str, str]] = [
        (
            "timetable_entries",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  )
DELETE FROM timetable_entries
WHERE section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "timetable_conflicts",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM timetable_conflicts
WHERE section_id IN (SELECT id FROM sections_y)
   OR subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "section_breaks",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  )
DELETE FROM section_breaks
WHERE section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "fixed_timetable_entries",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  )
DELETE FROM fixed_timetable_entries
WHERE section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "special_allotments",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  )
DELETE FROM special_allotments
WHERE section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "teacher_subject_sections",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM teacher_subject_sections
WHERE section_id IN (SELECT id FROM sections_y)
   OR subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "section_time_windows",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  )
DELETE FROM section_time_windows
WHERE section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "section_elective_blocks",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  blocks_y AS (
    SELECT b.id
    FROM elective_blocks b
    JOIN year y ON y.id = b.academic_year_id
    WHERE (%(program_code)s IS NULL OR b.program_id = (SELECT program_id FROM program))
  )
DELETE FROM section_elective_blocks
WHERE section_id IN (SELECT id FROM sections_y)
   OR block_id IN (SELECT id FROM blocks_y);
""",
        ),
        (
            "section_subjects",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM section_subjects
WHERE section_id IN (SELECT id FROM sections_y)
   OR subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "combined_group_sections",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  ),
  groups2_y AS (
    SELECT g.id
    FROM combined_groups g
    JOIN year y ON y.id = g.academic_year_id
    WHERE g.subject_id IN (SELECT id FROM subjects_y)
  )
DELETE FROM combined_group_sections
WHERE combined_group_id IN (SELECT id FROM groups2_y)
   OR section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "combined_subject_sections",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  ),
  groups_y AS (
    SELECT g.id
    FROM combined_subject_groups g
    JOIN year y ON y.id = g.academic_year_id
    WHERE g.subject_id IN (SELECT id FROM subjects_y)
  )
DELETE FROM combined_subject_sections
WHERE combined_group_id IN (SELECT id FROM groups_y)
   OR section_id IN (SELECT id FROM sections_y);
""",
        ),
        (
            "elective_block_subjects",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  ),
  blocks_y AS (
    SELECT b.id
    FROM elective_blocks b
    JOIN year y ON y.id = b.academic_year_id
    WHERE (%(program_code)s IS NULL OR b.program_id = (SELECT program_id FROM program))
  )
DELETE FROM elective_block_subjects
WHERE block_id IN (SELECT id FROM blocks_y)
   OR subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "track_subjects",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s)
DELETE FROM track_subjects
WHERE academic_year_id = (SELECT id FROM year)
  AND (%(program_code)s IS NULL OR program_id = (SELECT program_id FROM program));
""",
        ),
        (
            "teacher_subject_years",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM teacher_subject_years
WHERE academic_year_id = (SELECT id FROM year)
  AND subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "teacher_subjects",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM teacher_subjects
WHERE subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "combined_groups",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM combined_groups
WHERE academic_year_id = (SELECT id FROM year)
  AND subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "combined_subject_groups",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM combined_subject_groups
WHERE academic_year_id = (SELECT id FROM year)
  AND subject_id IN (SELECT id FROM subjects_y);
""",
        ),
        (
            "elective_blocks",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s)
DELETE FROM elective_blocks
WHERE academic_year_id = (SELECT id FROM year)
  AND (%(program_code)s IS NULL OR program_id = (SELECT program_id FROM program));
""",
        ),
        (
            "sections",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s)
DELETE FROM sections
WHERE academic_year_id = (SELECT id FROM year)
  AND (%(program_code)s IS NULL OR program_id = (SELECT program_id FROM program));
""",
        ),
        (
            "subjects",
            """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s)
DELETE FROM subjects
WHERE academic_year_id = (SELECT id FROM year)
  AND (%(program_code)s IS NULL OR program_id = (SELECT program_id FROM program));
""",
        ),
    ]

    if has_section_electives:
        deletes.append(
            (
                "section_electives",
                """
WITH
  year AS (SELECT id FROM academic_years WHERE year_number = %(year_number)s),
  program AS (SELECT id AS program_id FROM programs WHERE code = %(program_code)s),
  sections_y AS (
    SELECT s.id
    FROM sections s
    JOIN year y ON y.id = s.academic_year_id
    WHERE (%(program_code)s IS NULL OR s.program_id = (SELECT program_id FROM program))
  ),
  subjects_y AS (
    SELECT sub.id
    FROM subjects sub
    JOIN year y ON y.id = sub.academic_year_id
    WHERE (%(program_code)s IS NULL OR sub.program_id = (SELECT program_id FROM program))
  )
DELETE FROM section_electives
WHERE section_id IN (SELECT id FROM sections_y)
   OR subject_id IN (SELECT id FROM subjects_y);
""",
            )
        )

    results: dict[str, int] = {}
    for table_name, sql in deletes:
        cur.execute(sql, params)
        results[table_name] = cur.rowcount if cur.rowcount is not None else 0

    if delete_empty_runs:
        cur.execute(
            """
DELETE FROM timetable_runs tr
WHERE NOT EXISTS (SELECT 1 FROM timetable_entries te WHERE te.run_id = tr.id)
  AND NOT EXISTS (SELECT 1 FROM timetable_conflicts tc WHERE tc.run_id = tr.id)
  AND NOT EXISTS (SELECT 1 FROM section_breaks sb WHERE sb.run_id = tr.id);
"""
        )
        results["timetable_runs_empty"] = cur.rowcount if cur.rowcount is not None else 0

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "DEV ONLY: Delete all data scoped to an academic year (default: year 3). "
            "Supports optional filtering by program code."
        )
    )
    parser.add_argument("--year", type=int, default=3, help="Academic year number to delete (1-4). Default: 3")
    parser.add_argument(
        "--program-code",
        type=str,
        default=None,
        help="If set, only deletes data for this program code (e.g., BTECH_CSE).",
    )
    parser.add_argument(
        "--delete-empty-runs",
        action="store_true",
        help="Also delete timetable_runs that become completely empty after deletion.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually perform deletions (without this flag, the script only prints counts).",
    )

    args = parser.parse_args()

    if args.year < 1 or args.year > 4:
        raise SystemExit("--year must be between 1 and 4")

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    conninfo = _normalize_psycopg_url(database_url)
    with psycopg2.connect(conninfo) as conn:
        with conn.cursor() as cur:
            year_id = _fetch_one(cur, "SELECT id FROM academic_years WHERE year_number = %s", (args.year,))
            if year_id is None:
                raise SystemExit(f"No academic_years row found for year_number={args.year}")

            if args.program_code is not None:
                program_id = _fetch_one(cur, "SELECT id FROM programs WHERE code = %s", (args.program_code,))
                if program_id is None:
                    raise SystemExit(f"No programs row found for code={args.program_code!r}")

            _print_counts(cur, year_number=args.year, program_code=args.program_code)

            if not args.yes:
                print("Dry run only. Re-run with --yes to delete.")
                return 0

            results = _delete_year_data(
                cur,
                year_number=args.year,
                program_code=args.program_code,
                delete_empty_runs=args.delete_empty_runs,
            )

            print("Deleted rows:")
            for k, v in results.items():
                print(f"- {k}: {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
