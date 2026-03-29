#!/usr/bin/env python3
"""Delete specific teachers using raw SQL to bypass schema issues"""

import sys
from sqlalchemy import text

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal

def main():
    db = SessionLocal()
    try:
        # Teachers to delete
        teacher_codes = ["T10", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]
        
        print(f"🗑️  Deleting {len(teacher_codes)} teachers and their data using SQL...\n")
        
        # Get teacher IDs
        teacher_ids = []
        for code in teacher_codes:
            result = db.execute(
                text("SELECT id FROM teachers WHERE code = :code")
                , {"code": code}
            ).fetchall()
            teacher_ids.extend([row[0] for row in result])
        
        print(f"Found {len(teacher_ids)} teacher records to delete")
        
        if not teacher_ids:
            print("No teachers found!")
            return
        
        # Delete from timetable_entries
        result = db.execute(
            text("DELETE FROM timetable_entries WHERE teacher_id = ANY(:ids)"),
            {"ids": teacher_ids}
        )
        print(f"✅ Deleted {result.rowcount} timetable entries")
        
        # Delete from teacher_subject_sections
        result = db.execute(
            text("DELETE FROM teacher_subject_sections WHERE teacher_id = ANY(:ids)"),
            {"ids": teacher_ids}
        )
        print(f"✅ Deleted {result.rowcount} teacher assignments")
        
        # Delete conflicts referencing these teachers
        result = db.execute(
            text("DELETE FROM timetable_conflicts WHERE teacher_id = ANY(:ids)"),
            {"ids": teacher_ids}
        )
        print(f"✅ Deleted {result.rowcount} conflicts")
        
        # Delete the teachers
        result = db.execute(
            text("DELETE FROM teachers WHERE id = ANY(:ids)"),
            {"ids": teacher_ids}
        )
        print(f"✅ Deleted {result.rowcount} teachers")
        
        db.commit()
        print(f"\n✅ All done!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
