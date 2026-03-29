#!/usr/bin/env python3
"""Check what data exists in the database"""

import sys
from sqlalchemy import select

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal
from models import User, Program, Teacher, Section, AcademicYear

db = SessionLocal()

try:
    # Find user
    user = db.execute(
        select(User).where(User.username == "shivang123")
    ).scalar_one_or_none()
    
    if user:
        print(f"✅ User found: {user.username}")
        print(f"   ID: {user.id}")
        print(f"   Tenant ID: {user.tenant_id}")
        print(f"   Role: {user.role}\n")
    else:
        print("❌ User not found\n")
        sys.exit(1)
    
    # Count programs
    programs_all = db.execute(select(Program)).scalars().all()
    print(f"📊 All programs in DB: {len(programs_all)}\n")
    for p in programs_all[:5]:
        print(f"   - {p.code} ({p.name})")
        print(f"     Tenant: {p.tenant_id or 'SHARED'}")
    
    # Count teachers
    teachers_all = db.execute(select(Teacher)).scalars().all()
    print(f"\n👥 All teachers in DB: {len(teachers_all)}\n")
    for t in teachers_all[:5]:
        print(f"   - {t.code} ({t.full_name})")
        print(f"     Tenant: {t.tenant_id or 'SHARED'}")
    
    # Count sections
    sections_all = db.execute(select(Section)).scalars().all()
    print(f"\n📚 All sections in DB: {len(sections_all)}\n")
    for s in sections_all[:5]:
        print(f"   - {s.code} ({s.name})")
        print(f"     Tenant: {s.tenant_id or 'SHARED'}")
    
    # Count years
    years_all = db.execute(select(AcademicYear)).scalars().all()
    print(f"\n📅 All academic years in DB: {len(years_all)}\n")
    for y in years_all:
        print(f"   - Year {y.year_number}")
        print(f"     Tenant: {y.tenant_id or 'SHARED'}")
    
finally:
    db.close()
