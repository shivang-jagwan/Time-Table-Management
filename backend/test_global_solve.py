#!/usr/bin/env python
"""Direct global solve test - bypasses HTTP auth."""
from __future__ import annotations

import os
import sys
import uuid
import logging
from sqlalchemy.orm import Session

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import settings
from core.database import SessionLocal, ENGINE
from models.tenant import Tenant
from models.user import User
from models.program import Program
from solver.cp_sat_solver import solve_global_timetable
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Run a global solve test."""
    session = SessionLocal()
    try:
        # Find graphicerahill tenant
        q_tenant = select(Tenant).where(Tenant.code == "graphicerahill")
        tenant = session.execute(q_tenant).scalar_one_or_none()
        
        if not tenant:
            logger.error("Tenant 'graphicerahill' not found")
            return
        
        logger.info(f"Found tenant: {tenant.code} ({tenant.id})")
        
        # Find CSE program
        q_program = select(Program).where(
            (Program.code == "CSE") & (Program.tenant_id == tenant.id)
        )
        program = session.execute(q_program).scalar_one_or_none()
        
        if not program:
            logger.error("Program 'CSE' not found for this tenant")
            return
        
        logger.info(f"Found program: {program.code} ({program.id})")
        
        # Run solve
        logger.info("Starting global solve for year 3...")
        result = solve_global_timetable(
            db=session,
            program_id=program.id,
            academic_year_number=3,
            tenant_id=tenant.id,
            max_time_seconds=30,
            room_balance_mode='soft',
            relax_teacher_load_limits=False,
            require_optimal=False,
        )
        
        logger.info(f"Solve completed!")
        logger.info(f"  Status: {result.status}")
        logger.info(f"  Entries written: {result.entries_written}")
        logger.info(f"  Objective score: {result.objective_score}")
        logger.info(f"  Solve time: {result.solve_time_seconds}s")
        logger.info(f"  Warnings: {len(result.warnings)}")
        if result.warnings:
            for w in result.warnings[:5]:
                logger.info(f"    - {w}")
        
        logger.info(f"  Conflicts: {len(result.conflicts)}")
        if result.conflicts:
            for c in result.conflicts[:3]:
                logger.info(f"    - {c.conflict_type}: {c.message}")


# Fallback if SESSION import fails
try:
    from core.db import SESSION
except ImportError:
    def SESSION():
        from sqlalchemy.orm import sessionmaker
        return sessionmaker(bind=ENGINE)()


if __name__ == "__main__":
    main()
