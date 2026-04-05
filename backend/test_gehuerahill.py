#!/usr/bin/env python3
"""
Test script to run solver on gehuerahill program with observability.
"""

import sys
import json
from datetime import datetime
from sqlalchemy import select

sys.path.insert(0, str(__file__).replace('\\test_gehuerahill.py', ''))

from core.db import SessionLocal
from models.program import Program
from models.timetable_run import TimetableRun
from solver.cp_sat_solver import solve_program_global


def main():
    """Run solver on gehuerahill program."""
    
    db = SessionLocal()
    
    try:
        # 1. Find program by code or name
        program = db.execute(
            select(Program).where(
                (Program.code.ilike('%gehuerahill%')) | 
                (Program.name.ilike('%gehuerahill%'))
            ).limit(1)
        ).scalars().first()
        
        if not program:
            print("[ERROR] No program found matching 'gehuerahill'")
            print()
            print("Available programs:")
            all_programs = db.execute(select(Program).limit(10)).scalars().all()
            for p in all_programs:
                print(f"  - {p.code}: {p.name}")
            return
        
        print(f"[PROGRAM] {program.code}")
        print(f"   Name: {program.name}")
        print(f"   ID: {program.id}")
        print()
        
        # 2. Create new timetable run
        run = TimetableRun(
            tenant_id=program.tenant_id,
            status="CREATED",
            parameters={},
            notes="Solver test with observability - gehuerahill program",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        
        print(f"[RUN] TimetableRun created: {run.id}")
        print()
        
        # 3. Run solver
        print("STARTING SOLVER...")
        print("   Timeout: 120 seconds")
        print("   Observability: ENABLED")
        print()
        
        start_time = datetime.now()
        
        result = solve_program_global(
            db,
            run=run,
            program_id=program.id,
            seed=42,
            max_time_seconds=120,
            room_balance_mode="soft",
            enforce_teacher_load_limits=True,
            require_optimal=False,
            allow_extended_solve=False,
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        print(f"[SOLVER] Completed in {elapsed:.2f} seconds")
        print()
        
        # 4. Display result
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
            for i, w in enumerate(result.warnings[:10], 1):
                print(f"   {i}. {w}")
            if len(result.warnings) > 10:
                print(f"   ... and {len(result.warnings) - 10} more")
            print()
        
        # 5. Check observability data
        print("=" * 60)
        print("OBSERVABILITY DATA")
        print("=" * 60)
        
        db.refresh(run)
        
        if run.analytics_dict:
            analytics = run.analytics_dict
            print("[OK] Analytics recorded:")
            print(f"   CP-SAT Status:       {analytics.get('cp_sat_status')}")
            print(f"   Variables:           {analytics.get('variables_created')}")
            print(f"   Constraints:         {analytics.get('constraints_created')}")
            print(f"   Objective:           {analytics.get('total_objective_value')}")
            print(f"   Coverage:            {analytics.get('coverage_percentage'):.1f}%")
            print(f"   Room Util:           {analytics.get('room_utilization_percentage'):.1f}%")
            print(f"   Teacher Load Avg:    {analytics.get('teacher_average_load'):.1f}")
            print(f"   Section Load Avg:    {analytics.get('section_average_load'):.1f}")
            print()
            
            # Show penalties
            penalties = analytics.get('penalty_breakdown', {})
            total_penalty = analytics.get('penalty_total', 0)
            if total_penalty > 0:
                print("   Top Penalties:")
                sorted_penalties = sorted(
                    [(k, v) for k, v in penalties.items() if isinstance(v, (int, float)) and v > 0],
                    key=lambda x: x[1],
                    reverse=True
                )
                for name, value in sorted_penalties[:5]:
                    print(f"      {name}: {value}")
            else:
                print("   [No penalties]")
            
            print()
            
            # Show violations
            violations = analytics.get('violations', {})
            total_violations = analytics.get('violations_total', 0)
            if total_violations > 0:
                print("   Violations:")
                for name, count in violations.items():
                    if isinstance(count, (int, float)) and count > 0:
                        print(f"      {name}: {count}")
            else:
                print("   [No violations]")
        else:
            print("[WARNING] No analytics recorded")
        
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
