#!/usr/bin/env python3
"""Delete specific teachers and their associated entries from the database"""

import sys
from sqlalchemy import select

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal
from models import Teacher, TimetableEntry, TeacherSubjectSection

def main():
    db = SessionLocal()
    try:
        # Teachers to delete
        teacher_codes = ["T10", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"]
        
        print(f"🗑️  Deleting {len(teacher_codes)} teachers and their data...\n")
        
        deleted_count = 0
        entries_deleted = 0
        assignments_deleted = 0
        
        for code in teacher_codes:
            teachers = db.execute(
                select(Teacher).where(Teacher.code == code)
            ).scalars().all()
            
            if teachers:
                for teacher in teachers:
                    print(f"   ❌ {code} ({teacher.full_name}) - Tenant: {teacher.tenant_id or 'SHARED'}")
                    
                    # Delete timetable entries for this teacher
                    entries = db.execute(
                        select(TimetableEntry).where(TimetableEntry.teacher_id == teacher.id)
                    ).scalars().all()
                    
                    for entry in entries:
                        db.delete(entry)
                        entries_deleted += 1
                    
                    # Delete teacher-subject-section assignments
                    assignments = db.execute(
                        select(TeacherSubjectSection).where(TeacherSubjectSection.teacher_id == teacher.id)
                    ).scalars().all()
                    
                    for assignment in assignments:
                        db.delete(assignment)
                        assignments_deleted += 1
                    
                    # Delete teacher
                    db.delete(teacher)
                    deleted_count += 1
            else:
                print(f"   ⚠️  {code} - not found")
        
        db.commit()
        print(f"\n✅ Deleted {deleted_count} teachers, {entries_deleted} entries, {assignments_deleted} assignments!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
