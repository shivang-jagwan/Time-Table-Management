#!/usr/bin/env python3
"""Test solver with soft constraints enabled"""

import sys
import time
from datetime import datetime

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal
from models import Program, AcademicYear, TimetableRun
from sqlalchemy import select
from solver.cp_sat_solver import solve_program_year

db = SessionLocal()

try:
    # Find user's tenant and program
    from models import User
    user = db.execute(
        select(User).where(User.username == "shivang123")
    ).scalar_one_or_none()
    
    if not user:
        print("ERROR: User not found")
        sys.exit(1)
    
    print(f"[OK] User: {user.username} (Tenant: {user.tenant_id})")
    
    # Get program(s)
    programs = db.execute(
        select(Program).where(Program.tenant_id == user.tenant_id)
    ).scalars().all()
    
    if not programs:
        print("ERROR: No programs found for user")
        sys.exit(1)
    
    program = programs[0]
    print(f"[OK] Program: {program.code} ({program.name})")
    
    # Get academic year
    years = db.execute(
        select(AcademicYear)
        .where(AcademicYear.tenant_id == user.tenant_id)
        .order_by(AcademicYear.year_number)
    ).scalars().all()
    
    if not years:
        print("ERROR: No academic years found")
        sys.exit(1)
    
    year = years[0]
    print(f"[OK] Academic Year: {year.year_number}")
    
    # Create a test timetable run
    run = TimetableRun(
        tenant_id=user.tenant_id,
        academic_year_id=year.id,
        status="CREATED",
        seed=42,
    )
    db.add(run)
    db.commit()
    
    print(f"[TEST] Solver with soft constraints...")
    print(f"   Run ID: {run.id}\n")
    
    # Run solver
    start_time = time.time()
    result = solve_program_year(
        db=db,
        run=run,
        program_id=program.id,
        academic_year_id=year.id,
        seed=42,
        max_time_seconds=30.0,
        enforce_teacher_load_limits=True,
        require_optimal=False,
    )
    elapsed = time.time() - start_time
    
    print(f"\n[OK] Solver completed in {elapsed:.2f}s")
    print(f"   Status: {result.status}")
    print(f"   Entries written: {result.entries_written}")
    print(f"   Objective score: {result.objective_score}")
    print(f"   Conflicts: {len(result.conflicts)}")
    print(f"   Warnings: {len(result.warnings)}\n")
    
    if result.status == "MODEL_INVALID":
        print("FAILED: MODEL_INVALID detected - soft constraints not working")
        print(f"   Reason: {result.reason_summary}")
        sys.exit(1)
    elif result.status in ("FEASIBLE", "OPTIMAL"):
        print("SUCCESS: Model is feasible - soft constraints working!")
        if result.warnings:
            print(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings[:5]:
                print(f"  - {w}")
    else:
        print(f"WARNING: Status: {result.status}")
        if result.reason_summary:
            print(f"   Reason: {result.reason_summary}")
    
    # Update run status
    run.status = result.status
    db.commit()
    print(f"\n[OK] Run status updated to: {run.status}")
    
finally:
    db.close()
