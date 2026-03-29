#!/usr/bin/env python3
"""Check the details of the most recent failed run"""

import requests
import json

API_BASE = "http://localhost:8000/api"
USERNAME = "shivang123"
PASSWORD = "Shivang@GEHU123"

session = requests.Session()

# Login
resp = session.post(f"{API_BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD})
token = resp.json()['access_token']
session.headers.update({"Authorization": f"Bearer {token}"})

# Get latest runs
resp = session.get(f"{API_BASE}/solver/runs?limit=5")
if resp.status_code == 200:
    runs = resp.json().get('runs', [])
    if runs:
        latest_run = runs[0]  # Most recent
        run_id = latest_run['id']
        print(f"Latest run: {run_id}")
        print(f"Status: {latest_run.get('status')}")
        print(f"Notes: {latest_run.get('notes')}\n")
        
        # Get run details with conflicts
        resp = session.get(f"{API_BASE}/solver/runs/{run_id}")
        if resp.status_code == 200:
            run = resp.json()
            print("Run Details:")
            print(f"  Status: {run.get('status')}")
            print(f"  Notes: {run.get('notes')}")
            print(f"  Entries: {run.get('entries_total', 0)}")
            print(f"  Conflicts: {run.get('conflicts_total', 0)}")
            
            # Get conflicts
            resp_conflicts = session.get(f"{API_BASE}/solver/runs/{run_id}/conflicts")
            if resp_conflicts.status_code == 200:
                conflicts = resp_conflicts.json().get('conflicts', [])
                if conflicts:
                    print(f"\n  🔴 Conflicts ({len(conflicts)}):")
                    for c in conflicts[:5]:
                        print(f"    - [{c.get('severity')}] {c.get('conflict_type')}: {c.get('message', '-')[:100]}")
                    if len(conflicts) > 5:
                        print(f"    ... and {len(conflicts) - 5} more")
                else:
                    print("\n  ✅ No conflicts")
