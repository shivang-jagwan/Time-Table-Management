from __future__ import annotations

import os
from typing import Any

from fastapi.testclient import TestClient

from main import app


def _count_json(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        # common shape: { items: [...] }
        for key in ("items", "data", "results"):
            if key in value and isinstance(value[key], list):
                return len(value[key])
        return len(value)
    return 1


def main() -> None:
    client = TestClient(app)

    username = os.environ.get("SMOKE_USERNAME") or os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("SMOKE_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "Missing credentials. Set SMOKE_USERNAME+SMOKE_PASSWORD (or ADMIN_USERNAME+ADMIN_PASSWORD) to run this smoke test."
        )

    login = client.post("/api/auth/login", json={"username": username, "password": password})
    if login.status_code >= 400:
        raise SystemExit(f"FAIL /api/auth/login: {login.status_code} {login.text}")

    # Auth is cookie-based (HttpOnly). TestClient preserves cookies.
    auth_headers = {}

    # Discover a usable program_code and academic_year_number for this tenant.
    program_code = None
    academic_year_number = None
    programs_resp = client.get("/api/programs/", headers=auth_headers)
    if programs_resp.status_code < 400:
        try:
            programs_payload = programs_resp.json()
        except Exception:
            programs_payload = None
        if isinstance(programs_payload, list) and programs_payload:
            first = programs_payload[0]
            if isinstance(first, dict):
                program_code = first.get("code")

    years_resp = client.get("/api/admin/academic-years", headers=auth_headers)
    if years_resp.status_code < 400:
        try:
            years_payload = years_resp.json()
        except Exception:
            years_payload = None
        if isinstance(years_payload, list) and years_payload:
            # Common shapes: {"number": 3} or {"academic_year_number": 3}
            for y in years_payload:
                if not isinstance(y, dict):
                    continue
                n = y.get("number", y.get("academic_year_number"))
                if isinstance(n, int):
                    academic_year_number = n
                    break

    checks = [
        ("/health", None),
        ("/api/programs/", None),
        ("/api/teachers/", None),
        ("/api/rooms/", None),
        ("/api/solver/time-slots", None),
        ("/api/admin/academic-years", None),
    ]

    if program_code and academic_year_number is not None:
        checks.insert(
            5,
            ("/api/sections/", {"program_code": program_code, "academic_year_number": academic_year_number}),
        )

    for path, params in checks:
        if path == "/health":
            resp = client.get(path)
        else:
            resp = client.get(path, params=params, headers=auth_headers)
        try:
            payload = resp.json()
        except Exception:
            payload = resp.text

        if resp.status_code >= 400:
            raise SystemExit(f"FAIL {path}: {resp.status_code} {payload}")

        if path == "/health":
            print(f"OK {path}: {payload}")
        else:
            count = _count_json(payload)
            print(f"OK {path}: count={count}")

    # Solver smoke: with an empty dataset, we expect a clean error/validation/infeasible response
    # (but not a crash). This uses a minimal request shape.
    if program_code and academic_year_number is not None:
        solve_payload = {
            "program_code": program_code,
            "academic_year_number": academic_year_number,
            "max_time_seconds": 5.0,
            "require_optimal": True,
        }
        resp = client.post("/api/solver/solve", json=solve_payload, headers=auth_headers)
    elif program_code:
        # Fall back to a global generate call which does not require academic years.
        solve_payload = {
            "program_code": program_code,
            "seed": 1,
        }
        resp = client.post("/api/solver/generate-global", json=solve_payload, headers=auth_headers)
    else:
        print("SKIP solver smoke: no programs available for this tenant")
        return
    try:
        payload = resp.json()
    except Exception:
        payload = resp.text
    if resp.status_code >= 400:
        raise SystemExit(f"FAIL solver request: {resp.status_code} {payload}")

    status = payload.get("status") if isinstance(payload, dict) else None
    entries_written = payload.get("entries_written") if isinstance(payload, dict) else None
    conflicts = payload.get("conflicts") if isinstance(payload, dict) else None
    conflicts_count = len(conflicts) if isinstance(conflicts, list) else None
    first_conflict = None
    if isinstance(conflicts, list) and conflicts:
        first = conflicts[0]
        if isinstance(first, dict):
            ctype = first.get("conflict_type")
            msg = first.get("message")
            first_conflict = f"{ctype}: {msg}" if ctype or msg else str(first)
        else:
            first_conflict = str(first)

    suffix = f" first_conflict={first_conflict}" if first_conflict else ""
    if isinstance(payload, dict) and "run_id" in payload and "status" in payload and "entries_written" not in payload:
        # generate-global style response
        print(f"OK /api/solver/generate-global: status={status} run_id={payload.get('run_id')}")
    else:
        print(
            f"OK /api/solver/solve: status={status} entries_written={entries_written} conflicts={conflicts_count}" + suffix
        )


if __name__ == "__main__":
    main()
