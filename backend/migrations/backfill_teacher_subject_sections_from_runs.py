from __future__ import annotations

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
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def main() -> int:
    """Dev helper.

    Backfills strict teacher assignments (teacher_subject_sections) from existing
    timetable entries in FEASIBLE/OPTIMAL runs, then enforces fixed timetable
    entries as the authoritative assignment for their (section, subject).
    """

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    conninfo = _normalize_psycopg_url(database_url)

    sql_backfill_from_runs = """
    insert into teacher_subject_sections(teacher_id, subject_id, section_id, is_active)
    select distinct on (te.section_id, te.subject_id)
      te.teacher_id, te.subject_id, te.section_id, true
    from timetable_entries te
    join timetable_runs tr on tr.id = te.run_id
    where tr.status in ('FEASIBLE','OPTIMAL')
    order by te.section_id, te.subject_id, te.created_at desc
    on conflict (teacher_id, subject_id, section_id)
    do update set is_active = excluded.is_active;
    """

    sql_apply_fixed_precedence = """
    -- Deactivate any active assignments that conflict with fixed entries.
    update teacher_subject_sections t
    set is_active = false
    from fixed_timetable_entries fe
    where fe.is_active is true
      and t.section_id = fe.section_id
      and t.subject_id = fe.subject_id
      and t.is_active is true
      and t.teacher_id <> fe.teacher_id;

    -- Ensure the fixed (teacher, subject, section) assignment exists and is active.
    insert into teacher_subject_sections(teacher_id, subject_id, section_id, is_active)
    select fe.teacher_id, fe.subject_id, fe.section_id, true
    from fixed_timetable_entries fe
    where fe.is_active is true
    on conflict (teacher_id, subject_id, section_id)
    do update set is_active = excluded.is_active;
    """

    with psycopg2.connect(conninfo) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("select count(*) from teacher_subject_sections")
            before_total = int(cur.fetchone()[0])

            cur.execute(sql_backfill_from_runs)
            cur.execute(sql_apply_fixed_precedence)

            cur.execute("select count(*) from teacher_subject_sections")
            after_total = int(cur.fetchone()[0])
            cur.execute("select count(*) from teacher_subject_sections where is_active is true")
            after_active = int(cur.fetchone()[0])

    print(
        {
            "teacher_subject_sections_before_total": before_total,
            "after_total": after_total,
            "delta_total": after_total - before_total,
            "after_active": after_active,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
