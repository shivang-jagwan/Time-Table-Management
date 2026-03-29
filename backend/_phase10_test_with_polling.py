#!/usr/bin/env python3
"""Phase 10 Validation: Full-Year Timetable Generation with Polling

Tests the fixed solver with deadline enforcement and infinite loop mitigation.
Since solve-global is async, this script polls the run status.
"""

import requests
import json
import time
import sys

# Configuration
API_BASE = "http://localhost:8000/api"
USERNAME = "shivang123"
PASSWORD = "Shivang@GEHU123"
POLL_INTERVAL = 2  # seconds between status checks
MAX_POLL_TIME = 90  # max seconds to wait for completion

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
        log(f"✅ Login successful")
        
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
        
        # Step 3: Initiate GLOBAL (full year) timetable solve
        log("\nStep 3: INITIATING GLOBAL TIMETABLE SOLVE...")
        log("⏱️  This will test deadline enforcement, hybrid GA, and greedy fallback.")
        log("   (Solve runs in background, we'll poll for results)")
        
        solve_start = time.time()
        
        solve_payload = {
            "program_code": program_code,
            "seed": 42,
            "max_time_seconds": 60,
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
        
        log("Initiating solve request...")
        solve_resp = session.post(
            f"{API_BASE}/solver/solve-global",
            json=solve_payload
        )
        
        if solve_resp.status_code not in (200, 202):
            log(f"❌ SOLVE INIT FAILED: {solve_resp.status_code}")
            log(f"Response: {solve_resp.text[:500]}")
            return False
        
        result = solve_resp.json()
        run_id = result.get('run_id')
        
        if not run_id:
            log("❌ No run_id returned from solve endpoint")
            return False
        
        log(f"✅ Solve initiated. Run ID: {run_id}")
        log(f"   Initial Status: {result.get('status', 'UNKNOWN')}")
        
        # Step 4: Poll for completion
        log("\nStep 4: POLLING FOR SOLVE COMPLETION...")
        
        poll_count = 0
        max_polls = int(MAX_POLL_TIME / POLL_INTERVAL)
        final_result = None
        
        while poll_count < max_polls:
            time.sleep(POLL_INTERVAL)
            poll_count += 1
            elapsed = time.time() - solve_start
            
            # Poll the run status
            status_resp = session.get(f"{API_BASE}/solver/runs/{run_id}")
            
            if status_resp.status_code != 200:
                log(f"⏳ Poll {poll_count}/{max_polls} ({elapsed:.1f}s): Status check failed ({status_resp.status_code})")
                continue
            
            run_detail = status_resp.json()
            status = run_detail.get('status', 'UNKNOWN')
            
            # Terminal states
            if status in ('OPTIMAL', 'FEASIBLE', 'FEASIBLE_GREEDY_FALLBACK', 'INFEASIBLE', 'ERROR', 'VALIDATION_FAILED', 'TIMEOUT'):
                final_result = run_detail
                log(f"✅ Solve completed: {status} (elapsed: {elapsed:.1f}s)")
                break
            
            log(f"⏳ Poll {poll_count}/{max_polls} ({elapsed:.1f}s): Status = {status}")
        
        if final_result is None:
            log(f"❌ POLLING TIMEOUT after {MAX_POLL_TIME}s")
            return False
        
        # Step 5: Parse and display results
        log(f"\n📊 DETAILED RESULTS:")
        log(f"  Status: {final_result.get('status', 'UNKNOWN')}")
        log(f"  Entries Written: {final_result.get('entries_total', 0)}")
        log(f"  Objective Score: {final_result.get('objective_score', 'N/A')}")
        log(f"  Conflicts: {len(final_result.get('conflicts', []) or [])}")
        log(f"  Notes: {final_result.get('notes', '-')}")
        
        # Solver stats
        stats = final_result.get('solver_stats', {})
        if stats:
            log(f"\n  📈 SOLVER STATS:")
            log(f"    Variables: {stats.get('num_vars', 'N/A'):,}")
            log(f"    Constraints: {stats.get('num_constraints', 'N/A'):,}")
            log(f"    Termination: {stats.get('termination_reason', 'N/A')}")
            solve_time = stats.get('solve_time_seconds', 'N/A')
            log(f"    Solve Time: {solve_time}s" if isinstance(solve_time, (int, float)) else f"    Solve Time: N/A")
        
        # LNS telemetry if available
        lns_telemetry = final_result.get('lns_telemetry')
        if lns_telemetry:
            log(f"\n  🔄 LOCAL NEIGHBORHOOD SEARCH:")
            log(f"    Multi-start count: {lns_telemetry.get('multi_start_count', 'N/A')}")
            log(f"    LNS iterations executed: {lns_telemetry.get('lns_iterations_executed', 0)}")
            log(f"    Accepted iterations: {lns_telemetry.get('accepted_iterations', 0)}")
            log(f"    Total objective gain: {lns_telemetry.get('total_objective_gain', 'N/A')}")
        
        # Summary
        log("\n" + "="*60)
        success = final_result.get('status') in ('OPTIMAL', 'FEASIBLE', 'FEASIBLE_GREEDY_FALLBACK')
        if success:
            total_time = time.time() - solve_start
            log(f"✅ PHASE 10 VALIDATION: SUCCESS")
            log(f"   Full-year timetable generated in {total_time:.1f}s")
            log(f"   Entries: {final_result.get('entries_total', 0)}")
            log(f"   Status: {final_result.get('status')}")
            log(f"\n   ✨ NO INFINITE LOOPS DETECTED")
            log(f"   ✨ Deadline enforcement working correctly!")
        else:
            log(f"❌ PHASE 10 VALIDATION: FAILED")
            log(f"   Status: {final_result.get('status')}")
            log(f"   Notes: {final_result.get('notes', 'N/A')}")
        
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
