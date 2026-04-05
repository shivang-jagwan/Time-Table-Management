#!/usr/bin/env python3
"""
Test script to run solver with observability and check if it produces OPTIMAL or SUBOPTIMAL status.
"""

import sys
import asyncio
from datetime import datetime
from sqlalchemy import select

# Add to path
sys.path.insert(0, str(__file__).replace('\\test_observability_solve.py', ''))

from core.db import SessionLocal
from models.program import Program
from models.timetable_run import TimetableRun
from solver.cp_sat_solver import solve_program_global
import json


def main():
    """Run solver and check observability integration."""
    
    db = SessionLocal()
    
    try:
        # 1. Get first available program
        program = db.execute(
            select(Program).limit(1)
        ).scalars().first()
        
        if not program:
            print("ERROR: No programs found in database")
            print("   Run seed migration first")
            return
        
        print(f"[PROGRAM] {program.code} ({program.name})")
        print(f"   ID: {program.id}")
        print()
        
        # 2. Create new timetable run
        run = TimetableRun(
            tenant_id=program.tenant_id,
            status="CREATED",
            parameters={},
            notes="Solver test with observability integration",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        
        print(f"[RUN] TimetableRun created: {run.id}")
        print()
        
        # 3. Run solver
        print("STARTING SOLVER...")
        print("   Timeout: 30 seconds")
        print("   Observability: ENABLED (analytics + pre-solve + logging)")
        print()
        
        start_time = datetime.now()
        
        result = solve_program_global(
            db,
            run=run,
            program_id=program.id,
            seed=42,
            max_time_seconds=30,
            room_balance_mode="soft",
            enforce_teacher_load_limits=True,
            require_optimal=False,
            allow_extended_solve=False,
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"[SOLVER] Completed in {elapsed:.2f} seconds")
        print()
        
        # 4. Check result status
        print("=" * 60)
        print("SOLVER RESULT")
        print("=" * 60)
        print(f"Status:              {result.status}")
        print(f"Entries written:     {result.entries_written}")
        print(f"Objective score:     {result.objective_score}")
        print(f"Best bound:          {result.best_objective_bound}")
        if result.optimality_gap is not None:
            print(f"Optimality gap:      {result.optimality_gap}")
        print(f"Solve time (sec):    {result.solve_time_seconds:.2f}")
        print(f"Message:             {result.message}")
        print()
        
        if result.warnings:
            print("WARNINGS:")
            for i, w in enumerate(result.warnings[:5], 1):
                print(f"   {i}. {w}")
            if len(result.warnings) > 5:
                print(f"   ... and {len(result.warnings) - 5} more")
            print()
        
        # 5. Check observability data
        print("=" * 60)
        print("OBSERVABILITY DATA")
        print("=" * 60)
        
        db.refresh(run)
        
        if run.analytics_dict:
            analytics = run.analytics_dict
            print("[OK] Analytics recorded:")
            print(f"   Variables created:     {analytics.get('variables_created', '?')}")
            print(f"   Constraints created:   {analytics.get('constraints_created', '?')}")
            print(f"   Coverage %:            {analytics.get('coverage_percentage', '?')}%")
            print(f"   Room utilization %:    {analytics.get('room_utilization_percentage', '?')}%")
            
            if analytics.get('penalty_breakdown'):
                print()
                print("   Top penalties:")
                penalties = analytics['penalty_breakdown']
                top_items = sorted(
                    [(k, v) for k, v in penalties.items() if isinstance(v, (int, float))],
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                for name, value in top_items:
                    if value > 0:
                        print(f"      {name}: {value}")
            
            if analytics.get('violations'):
                print()
                print("   Violations:")
                violations = analytics['violations']
                for name, count in violations.items():
                    if isinstance(count, (int, float)) and count > 0:
                        print(f"      {name}: {count}")
        else:
            print("[WARNING] No analytics recorded (database migration may be pending)")
        
        print()
        
        # 6. Final status
        print("=" * 60)
        if result.status in ("OPTIMAL", "FEASIBLE"):
            print(f"[SUCCESS] Solver returned {result.status}")
            print(f"   Generated {result.entries_written} timetable entries")
        else:
            print(f"[INCOMPLETE] Solver returned {result.status}")
            print(f"   Generated {result.entries_written} timetable entries")
        print("=" * 60)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
