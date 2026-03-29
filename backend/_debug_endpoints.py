#!/usr/bin/env python3
"""Debug: Test individual endpoints without full solve flow"""

import requests
import json

API_BASE = "http://localhost:8000/api"
USERNAME = "shivang123"
PASSWORD = "Shivang@GEHU123"

session = requests.Session()

# Login
print("[1] Login...")
resp = session.post(f"{API_BASE}/auth/login", json={"username": USERNAME, "password": PASSWORD})
print(f"    Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"    Error: {resp.text}")
    exit(1)

token = resp.json()['access_token']
session.headers.update({"Authorization": f"Bearer {token}"})

# Get programs
print("[2] Get programs...")
resp = session.get(f"{API_BASE}/programs")
print(f"    Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"    Error: {resp.text}")
    exit(1)
programs = resp.json()
program_code = programs[0]["code"] if programs else None
print(f"    Program: {program_code}")

# Try generate-global (just creation, no solve)
print("[3] Generate-global (create run without solving)...")
payload = {"program_code": program_code, "seed": 42}
resp = session.post(f"{API_BASE}/solver/generate-global", json=payload)
print(f"    Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"    Error: {resp.text[:500]}")
else:
    result = resp.json()
    print(f"    Run created: {result.get('run_id', 'N/A')}")
    print(f"    Status: {result.get('status', 'N/A')}")

# Try solve-global (this is where it crashes)
print("\n[4] Solve-global (the crashing endpoint)...")
payload = {
    "program_code": program_code,
    "seed": 42,
    "max_time_seconds": 60,
    "relax_teacher_load_limits": False,
    "require_optimal": False,
}
print(f"    Payload: {json.dumps(payload, indent=2)}")
print("    Sending...")
try:
    resp = session.post(f"{API_BASE}/solver/solve-global", json=payload, timeout=15)
    print(f"    Status: {resp.status_code}")
    if resp.status_code in (200, 202):
        result = resp.json()
        print(f"    Run ID: {result.get('run_id', 'N/A')}")
        print(f"    Status: {result.get('status', 'N/A')}")
    else:
        print(f"    Error: {resp.text[:500]}")
except requests.RequestException as e:
    print(f"    ❌ Request failed: {type(e).__name__}: {str(e)[:200]}")

print("\nDone.")
