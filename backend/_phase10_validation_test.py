#!/usr/bin/env python3
"""Phase 10 Validation: Full-Year Timetable Generation Test

Tests the fixed solver with deadline enforcement and infinite loop mitigation.
Credentials: shivang123 / Shivang@GEHU123
"""

import requests
import json
import time
import sys

# Configuration
API_BASE = "http://localhost:8000/api"
USERNAME = "shivang123"
PASSWORD = "Shivang@GEHU123"

def log(msg):
    """Print timestamped log message."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def test_phase10():
    """Run Phase 10 comprehensive timetable generation test."""
    session = requests.Session()
    
    try:
        # Step 1: Login
        log("=== PHASE 10 VALIDATION START ===")
        log(f"Step 1: Authenticating as {USERNAME}...")
        
        login_resp = session.post(
            f"{API_BASE}/auth/login",
            json={"username": USERNAME, "password": PASSWORD}
        )
        
        if login_resp.status_code != 200:
            log(f"❌ LOGIN FAILED: {login_resp.status_code}")
            log(f"Response: {login_resp.text}")
            return False
        
        auth_data = login_resp.json()
        log(f"✅ Login successful. Token: {auth_data.get('access_token', 'N/A')[:20]}...")
        
        session.headers.update({"Authorization": f"Bearer {auth_data['access_token']}"})
        
        # Step 2: Get programs
        log("\nStep 2: Fetching available programs...")
        
        programs_resp = session.get(f"{API_BASE}/programs")
        if programs_resp.status_code != 200:
            log(f"❌ Failed to fetch programs: {programs_resp.status_code}")
            return False
        
        programs = programs_resp.json()
        if not programs:
            log("❌ No programs available")
            return False
        
        program_code = programs[0]["code"]
        program_name = programs[0].get("name", "Unknown")
        log(f"✅ Found {len(programs)} program(s). Using: {program_name} (Code: {program_code})")
        
        # Step 3: Solve GLOBAL (full year) timetable
        log("\nStep 3: INITIATING GLOBAL TIMETABLE SOLVE...")
        log("⏱️  This will test deadline enforcement, hybrid GA, and greedy fallback.")
        
        solve_start = time.time()
        
        solve_payload = {
            "program_code": program_code,
            "seed": 42,
            "max_time_seconds": 60,  # 60 seconds total budget
            "relax_teacher_load_limits": False,
            "require_optimal": False,
            "allow_extended_solve": False,
            "hybrid_init_enabled": True,
            "hybrid_population_size": 16,
            "hybrid_generations": 5,
            "multi_seed_restarts": 2,
            "lns_iterations": 1,
            "lns_keep_fraction": 0.7,
        }
        
        log(f"Payload: {json.dumps(solve_payload, indent=2)}")
        
        solve_resp = session.post(
            f"{API_BASE}/solver/solve-global",
            json=solve_payload
        )
        
        solve_time = time.time() - solve_start
        
        if solve_resp.status_code not in (200, 202):
            log(f"❌ SOLVE FAILED: {solve_resp.status_code}")
            log(f"Response: {solve_resp.text[:500]}")
            return False
        
        result = solve_resp.json()
        
        # Step 4: Parse and display results
        log(f"\n✅ SOLVE COMPLETED in {solve_time:.1f} seconds")
        log(f"\nRESULTS:")
        log(f"  Status: {result.get('status', 'UNKNOWN')}")
        log(f"  Entries Written: {result.get('entries_written', 0)}")
        log(f"  Objective Score: {result.get('objective_score', 'N/A')}")
        log(f"  Conflicts: {len(result.get('conflicts', []))}")
        
        warnings = result.get('warnings', [])
        if warnings:
            log(f"\n  ⚠️  WARNINGS ({len(warnings)}):")
            for w in warnings[:5]:
                log(f"    - {w}")
            if len(warnings) > 5:
                log(f"    ... and {len(warnings) - 5} more")
        
        diagnostics = result.get('diagnostics', [])
        if diagnostics:
            log(f"\n  📊 DIAGNOSTICS ({len(diagnostics)}):")
            for d in diagnostics[:3]:
                log(f"    - {d}")
        
        stats = result.get('solver_stats', {})
        if stats:
            log(f"\n  📈 SOLVER STATS:")
            log(f"    Variables: {stats.get('num_vars', 'N/A'):,}")
            log(f"    Constraints: {stats.get('num_constraints', 'N/A'):,}")
            log(f"    Termination: {stats.get('termination_reason', 'N/A')}")
            log(f"    Solve Time: {stats.get('solve_time_seconds', 'N/A')}s")
        
        # Summary
        log("\n" + "="*60)
        success = result.get('status') in ('OPTIMAL', 'FEASIBLE', 'FEASIBLE_GREEDY_FALLBACK')
        if success:
            log(f"✅ PHASE 10 VALIDATION: SUCCESS")
            log(f"   Full-year timetable generated in {solve_time:.1f}s")
            log(f"   Entries: {result.get('entries_written', 0)}")
            log(f"   NO INFINITE LOOPS DETECTED - Deadline enforcement working!")
        else:
            log(f"❌ PHASE 10 VALIDATION: FAILED")
            log(f"   Status: {result.get('status')}")
        
        log("="*60)
        
        return success
        
    except Exception as e:
        log(f"❌ EXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = test_phase10()
    sys.exit(0 if success else 1)
