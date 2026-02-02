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

    checks = [
        ("/health", None),
        ("/api/programs/", None),
        ("/api/teachers/", None),
        ("/api/rooms/", None),
        ("/api/solver/time-slots", None),
        ("/api/sections/", {"program_code": "CSE", "academic_year_number": 3}),
        ("/api/admin/academic-years", None),
    ]

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
    solve_payload = {
        "program_code": "CSE",
        "academic_year_number": 3,
        "max_time_seconds": 5.0,
        "require_optimal": True,
    }
    resp = client.post("/api/solver/solve", json=solve_payload, headers=auth_headers)
    try:
        payload = resp.json()
    except Exception:
        payload = resp.text
    if resp.status_code >= 400:
        raise SystemExit(f"FAIL /api/solver/solve: {resp.status_code} {payload}")

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
    print(
        f"OK /api/solver/solve: status={status} entries_written={entries_written} conflicts={conflicts_count}" + suffix
    )


if __name__ == "__main__":
    main()
