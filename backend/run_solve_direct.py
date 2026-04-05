#!/usr/bin/env python
"""
Direct solve invocation using backend Python context.
This script activates the venv, sets up PYTHONPATH, then runs the solve.
"""
import subprocess
import sys
import os

# Run using the venv's Python
venv_python = r"d:\timetable\backend\.venv\Scripts\python.exe"

script = """
import os
import sys
os.chdir(r'd:\\timetable\\backend')
sys.path.insert(0, '.')

from core.database import SessionLocal
from models.tenant import Tenant
from models.program import Program
from solver.cp_sat_solver import solve_program_global
from models.timetable_run import TimetableRun
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

session = SessionLocal()
try:
    # List all tenants
    q_all_tenants = select(Tenant)
    all_tenants = session.execute(q_all_tenants).scalars().all()
    print(f"📊 Found {len(all_tenants)} tenants:")
    for t in all_tenants[:10]:
        print(f"   - {t.name}")
    
    # Find tenant by name (fallback to first if not found)
    tenant = None
    for t in all_tenants:
        if "graphic" in str(t.name).lower() or "era" in str(t.name).lower():
            tenant = t
            break
    
    if not tenant and all_tenants:
        tenant = all_tenants[0]
        print(f"⚠️ Falling back to first tenant: {tenant.name}")
    
    if not tenant:
        print("❌ No tenants found in database")
        sys.exit(1)
    
    # Find program
    q_prog = select(Program).where(
        (Program.code == "CSE") & (Program.tenant_id == tenant.id)
    )
    program = session.execute(q_prog).scalar_one_or_none()
    if not program:
        print("❌ Program not found")
        sys.exit(1)
    
    print(f"✅ Found tenant: {tenant.name}, program: {program.code}")
    print(f"🚀 Starting global solve for year 3...")
    
    result = solve_program_global(
        db=session,
        program_id=program.id,
        academic_year_number=3,
        tenant_id=tenant.id,
        max_time_seconds=30,
        room_balance_mode='soft',
        relax_teacher_load_limits=False,
        require_optimal=False,
    )
    
    print(f"✅ Solve completed!")
    print(f"📊 Status: {result.status}")
    print(f"📝 Entries: {result.entries_written}")
    print(f"🎯 Objective: {result.objective_score}")
    print(f"⏱️ Time: {result.solve_time_seconds}s")
    print(f"⚠️ Warnings: {len(result.warnings)}")
    for w in result.warnings[:3]:
        print(f"   - {w}")
    
    print(f"\\n✅ SUCCESS - Solve status: {result.status}")
    sys.exit(0)
    
finally:
    session.close()
"""

cmd = [venv_python, "-c", script]
result = subprocess.run(cmd, cwd=r'd:\timetable\backend', capture_output=False)
sys.exit(result.returncode)
