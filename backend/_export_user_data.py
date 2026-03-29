#!/usr/bin/env python3
"""Export all data for user shivang123 from database to JSON files"""

import sys
import json
from pathlib import Path
from sqlalchemy import select
from datetime import datetime

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal
from models import (
    User, Program, Teacher, Section, Subject, Room, TimeSlot,
    TeacherSubjectSection, SectionSubject, TimetableRun, TimetableEntry,
    AcademicYear
)

def serialize_obj(obj):
    """Convert SQLAlchemy object to dict"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            if not key.startswith('_'):
                result[key] = serialize_obj(value)
        return result
    return str(obj)

def export_data():
    db = SessionLocal()
    output_dir = Path('exports')
    output_dir.mkdir(exist_ok=True)
    
    try:
        # Find user
        user = db.execute(
            select(User).where(User.username == "shivang123")
        ).scalar_one_or_none()
        
        if not user:
            print("❌ User shivang123 not found")
            return
        
        print(f"✅ Found user: {user.username} (ID: {user.id})\n")
        
        # Get all programs for this user
        programs = db.execute(
            select(Program).where(Program.tenant_id == user.tenant_id)
        ).scalars().all()
        
        print(f"📊 Found {len(programs)} program(s)\n")
        
        for program in programs:
            print(f"Processing program: {program.code} ({program.name})")
            
            program_dir = output_dir / program.code
            program_dir.mkdir(exist_ok=True)
            
            # Get all academic years for this program
            years = db.execute(
                select(AcademicYear)
                .where(AcademicYear.tenant_id == user.tenant_id)
                .order_by(AcademicYear.year_number)
            ).scalars().all()
            
            print(f"  Found {len(years)} academic year(s)")
            
            for year in years:
                year_dir = program_dir / f"Year{year.year_number}"
                year_dir.mkdir(exist_ok=True)
                
                print(f"  \n  Year {year.year_number}:")
                
                # Export teachers
                teachers = db.execute(
                    select(Teacher)
                    .where(Teacher.tenant_id == user.tenant_id)
                    .order_by(Teacher.code)
                ).scalars().all()
                
                teachers_data = [
                    {
                        'id': str(t.id),
                        'code': t.code,
                        'full_name': t.full_name,
                        'email': getattr(t, 'email', None),
                        'is_active': t.is_active,
                        'weekly_off_day': getattr(t, 'weekly_off_day', None),
                        'max_per_day': getattr(t, 'max_per_day', None),
                        'max_per_week': getattr(t, 'max_per_week', None),
                    }
                    for t in teachers
                ]
                with open(year_dir / 'teachers.json', 'w') as f:
                    json.dump(teachers_data, f, indent=2)
                print(f"    ✅ Exported {len(teachers_data)} teachers")
                
                # Export sections
                sections = db.execute(
                    select(Section)
                    .where(Section.tenant_id == user.tenant_id)
                    .where(Section.academic_year_id == year.id)
                    .order_by(Section.code)
                ).scalars().all()
                
                sections_data = [
                    {
                        'id': str(s.id),
                        'code': s.code,
                        'name': s.name,
                        'track': s.track,
                        'is_active': s.is_active,
                        'academic_year_number': year.year_number,
                    }
                    for s in sections
                ]
                with open(year_dir / 'sections.json', 'w') as f:
                    json.dump(sections_data, f, indent=2)
                print(f"    ✅ Exported {len(sections_data)} sections")
                
                # Export subjects
                subjects = db.execute(
                    select(Subject)
                    .where(Subject.tenant_id == user.tenant_id)
                    .where(Subject.academic_year_id == year.id)
                    .order_by(Subject.code)
                ).scalars().all()
                
                subjects_data = [
                    {
                        'id': str(s.id),
                        'code': s.code,
                        'name': s.name,
                        'subject_type': str(s.subject_type),
                        'is_active': s.is_active,
                        'duration_slots': getattr(s, 'duration_slots', None),
                        'lab_block_size_slots': getattr(s, 'lab_block_size_slots', None),
                    }
                    for s in subjects
                ]
                with open(year_dir / 'subjects.json', 'w') as f:
                    json.dump(subjects_data, f, indent=2)
                print(f"    ✅ Exported {len(subjects_data)} subjects")
                
                # Export rooms
                rooms = db.execute(
                    select(Room)
                    .where(Room.tenant_id == user.tenant_id)
                    .order_by(Room.code)
                ).scalars().all()
                
                rooms_data = [
                    {
                        'id': str(r.id),
                        'code': r.code,
                        'name': r.name,
                        'room_type': str(r.room_type),
                        'capacity': getattr(r, 'capacity', None),
                        'is_special': getattr(r, 'is_special', False),
                        'is_active': r.is_active,
                    }
                    for r in rooms
                ]
                with open(year_dir / 'rooms.json', 'w') as f:
                    json.dump(rooms_data, f, indent=2)
                print(f"    ✅ Exported {len(rooms_data)} rooms")
                
                # Export time slots
                slots = db.execute(
                    select(TimeSlot)
                    .where(TimeSlot.tenant_id == user.tenant_id)
                    .order_by(TimeSlot.day_of_week, TimeSlot.slot_index)
                ).scalars().all()
                
                slots_data = [
                    {
                        'id': str(s.id),
                        'day_of_week': s.day_of_week,
                        'slot_index': s.slot_index,
                        'start_time': s.start_time.isoformat() if hasattr(s.start_time, 'isoformat') else str(s.start_time),
                        'end_time': s.end_time.isoformat() if hasattr(s.end_time, 'isoformat') else str(s.end_time),
                    }
                    for s in slots
                ]
                with open(year_dir / 'time_slots.json', 'w') as f:
                    json.dump(slots_data, f, indent=2)
                print(f"    ✅ Exported {len(slots_data)} time slots")
                
                # Export teacher-subject-section assignments
                assignments = db.execute(
                    select(TeacherSubjectSection)
                    .where(TeacherSubjectSection.tenant_id == user.tenant_id)
                    .order_by(TeacherSubjectSection.teacher_id)
                ).scalars().all()
                
                assignments_data = [
                    {
                        'id': str(a.id),
                        'teacher_id': str(a.teacher_id),
                        'subject_id': str(a.subject_id),
                        'section_id': str(a.section_id),
                        'is_active': a.is_active,
                    }
                    for a in assignments
                ]
                with open(year_dir / 'teacher_assignments.json', 'w') as f:
                    json.dump(assignments_data, f, indent=2)
                print(f"    ✅ Exported {len(assignments_data)} teacher assignments")
                
                # Export section-subject mappings
                section_subjects = db.execute(
                    select(SectionSubject)
                    .where(SectionSubject.tenant_id == user.tenant_id)
                    .order_by(SectionSubject.section_id)
                ).scalars().all()
                
                section_subjects_data = [
                    {
                        'id': str(ss.id),
                        'section_id': str(ss.section_id),
                        'subject_id': str(ss.subject_id),
                        'is_active': ss.is_active,
                    }
                    for ss in section_subjects
                ]
                with open(year_dir / 'section_subjects.json', 'w') as f:
                    json.dump(section_subjects_data, f, indent=2)
                print(f"    ✅ Exported {len(section_subjects_data)} section-subject mappings")
                
                # Export solver runs
                runs = db.execute(
                    select(TimetableRun)
                    .where(TimetableRun.tenant_id == user.tenant_id)
                    .order_by(TimetableRun.created_at.desc())
                ).scalars().all()
                
                runs_data = [
                    {
                        'id': str(r.id),
                        'status': r.status,
                        'seed': r.seed,
                        'created_at': r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
                        'notes': r.notes,
                    }
                    for r in runs
                ]
                with open(year_dir / 'solver_runs.json', 'w') as f:
                    json.dump(runs_data, f, indent=2)
                print(f"    ✅ Exported {len(runs_data)} solver runs")
                
                # Export timetable entries (only latest run)
                if runs:
                    latest_run = runs[0]
                    entries = db.execute(
                        select(TimetableEntry)
                        .where(TimetableEntry.run_id == latest_run.id)
                        .order_by(TimetableEntry.section_id, TimetableEntry.slot_id)
                    ).scalars().all()
                    
                    entries_data = [
                        {
                            'id': str(e.id),
                            'section_id': str(e.section_id),
                            'subject_id': str(e.subject_id),
                            'teacher_id': str(e.teacher_id),
                            'room_id': str(e.room_id),
                            'slot_id': str(e.slot_id),
                            'created_at': e.created_at.isoformat() if hasattr(e.created_at, 'isoformat') else str(e.created_at),
                        }
                        for e in entries
                    ]
                    with open(year_dir / 'timetable_entries.json', 'w') as f:
                        json.dump(entries_data, f, indent=2)
                    print(f"    ✅ Exported {len(entries_data)} timetable entries (from latest run)")
        
        print(f"\n\n✅ All data exported to: {output_dir}")
        print(f"   📁 Structure: exports/PROGRAM_CODE/YearN/")
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    export_data()
