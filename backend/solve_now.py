#!/usr/bin/env python
"""Direct solve invocation for testing."""
import subprocess
import sys

code = r"""
import os, sys, uuid
os.chdir(r'd:\timetable\backend')
sys.path.insert(0, '.')

from core.database import SessionLocal
from models.tenant import Tenant
from models.program import Program
from models.timetable_run import TimetableRun
from solver.cp_sat_solver import solve_program_global
from sqlalchemy import select

session = SessionLocal()
try:
    # Find all tenants
    all_tenants = session.execute(select(Tenant)).scalars().all()
    print(f"[INFO] Found {len(all_tenants)} tenants")
    
    # Find graphicerahill
    tenant = None
    for t in all_tenants:
        if "graphic" in str(t.name).lower():
            tenant = t
            break
    
    if not tenant:
        print("[ERROR] Tenant not found")
        sys.exit(1)
    
    print(f"[OK] Tenant: {tenant.name}")
    
    # Find CSE program
    program = session.execute(
        select(Program).where(
            (Program.code == "CSE") & (Program.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    
    if not program:
        print("[ERROR] Program CSE not found")
        sys.exit(1)
    
    print(f"[OK] Program: {program.code}")
    
    # Create run object
    run = TimetableRun(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        academic_year_id=None,
        status="CREATED",
        seed=None,
        parameters={"program_code": "CSE"},
        notes=None,
    )
    session.add(run)
    session.flush()
    print(f"[OK] Run created: {run.id}")
    
    # Call solver
    print(f"[RUNNING] Solver starting...")
    result = solve_program_global(
        db=session,
        run=run,
        program_id=program.id,
        seed=None,
        max_time_seconds=30,
        room_balance_mode='soft',
        enforce_teacher_load_limits=True,
        require_optimal=False,
    )
    
    print(f"\n[COMPLETE] SOLVE COMPLETE")
    print(f"Status: {result.status}")
    print(f"Entries: {result.entries_written}")
    print(f"Objective: {result.objective_score}")
    if result.solve_time_seconds is not None:
        print(f"Time: {result.solve_time_seconds:.1f}s")
    else:
        print(f"Time: N/A")
    print(f"Warnings: {len(result.warnings)}")
    
    if result.reason_summary:
        print(f"\nReason: {result.reason_summary}")
    
    if result.message:
        print(f"Message: {result.message}")
    
    if result.warnings:
        print(f"\nFirst 3 warnings:")
        for w in result.warnings[:3]:
            print(f"  - {w}")
    
finally:
    session.close()
"""

result = subprocess.run(
    [r"d:\timetable\backend\.venv\Scripts\python.exe", "-c", code],
    cwd=r"d:\timetable\backend"
)
sys.exit(result.returncode)
