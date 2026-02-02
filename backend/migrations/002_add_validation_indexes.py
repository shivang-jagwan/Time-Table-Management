from __future__ import annotations

"""Add DB indexes to speed up validation/solver reads.

Safe to run multiple times (uses IF NOT EXISTS).

Run:
  python -m migrations.002_add_validation_indexes --yes

Or:
  python backend/migrations/002_add_validation_indexes.py --yes
"""

import argparse
import sys
from pathlib import Path

# Allow running this script from any working directory.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text

from core.database import ENGINE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="Actually apply changes")
    args = parser.parse_args()

    statements = [
        # Core scoping / list endpoints
        "CREATE INDEX IF NOT EXISTS idx_sections_program_year_active ON sections (program_id, academic_year_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_rooms_active_special_type ON rooms (is_active, is_special, room_type);",
        "CREATE INDEX IF NOT EXISTS idx_time_slots_day_index ON time_slots (day_of_week, slot_index);",

        # Validation + solver joins
        "CREATE INDEX IF NOT EXISTS idx_section_subjects_section ON section_subjects (section_id);",
        "CREATE INDEX IF NOT EXISTS idx_section_subjects_subject ON section_subjects (subject_id);",
        "CREATE INDEX IF NOT EXISTS idx_section_subjects_section_subject ON section_subjects (section_id, subject_id);",

        "CREATE INDEX IF NOT EXISTS idx_section_time_windows_section_day ON section_time_windows (section_id, day_of_week);",

        "CREATE INDEX IF NOT EXISTS idx_teacher_subject_sections_section_active ON teacher_subject_sections (section_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_teacher_subject_sections_teacher_active ON teacher_subject_sections (teacher_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_teacher_subject_sections_subject_active ON teacher_subject_sections (subject_id, is_active);",

        "CREATE INDEX IF NOT EXISTS idx_special_allotments_section_active ON special_allotments (section_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_special_allotments_slot_active ON special_allotments (slot_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_fixed_entries_section_active ON fixed_timetable_entries (section_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_fixed_entries_slot_active ON fixed_timetable_entries (slot_id, is_active);",

        # Conflicts UI
        "CREATE INDEX IF NOT EXISTS idx_timetable_conflicts_run ON timetable_conflicts (run_id);",
        "CREATE INDEX IF NOT EXISTS idx_timetable_conflicts_type ON timetable_conflicts (conflict_type);",

        # Track subjects
        "CREATE INDEX IF NOT EXISTS idx_track_subjects_program_year_track ON track_subjects (program_id, academic_year_id, track);",
    ]

    if not args.yes:
        print("Dry run. Re-run with --yes to apply.")
        for s in statements:
            print("---")
            print(s.strip())
        return

    with ENGINE.begin() as conn:
        for s in statements:
            conn.execute(text(s))

    print(f"OK: created/verified {len(statements)} indexes.")


if __name__ == "__main__":
    main()
