from __future__ import annotations

"""Smoke test: ensure the two seeded admins are tenant-isolated.

This logs in as:
  - DeepaliDon / Deepalidon@always
  - chotapaaji / chotasardar

And verifies:
  - Each can create the same program code in their own tenant
  - Each sees a different program id
  - Cross-tenant mutation by id is blocked (404)

Run:
  python backend/_diag_seeded_admin_isolation_smoke.py
"""

import sys
from typing import Any

from fastapi.testclient import TestClient

from main import app


def _json(resp) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text


def _expect(resp, ok: set[int], *, context: str) -> Any:
    payload = _json(resp)
    if resp.status_code not in ok:
        raise SystemExit(f"FAIL {context}: {resp.status_code} {payload}")
    return payload


def _login(client: TestClient, *, username: str, password: str) -> None:
    # No tenant field on purpose: backend should infer tenant uniquely by username.
    _expect(
        client.post("/api/auth/login", json={"username": username, "password": password}),
        {200},
        context=f"POST /api/auth/login user={username!r}",
    )


def main() -> None:
    c1 = TestClient(app)
    c2 = TestClient(app)

    _login(c1, username="DeepaliDon", password="Deepalidon@always")
    _login(c2, username="chotapaaji", password="chotasardar")

    code = "ISO_TENANT"

    # Same code should be allowed in both tenants.
    r1 = c1.post("/api/programs/", json={"code": code, "name": f"{code} (A1)"})
    if r1.status_code not in {200, 201, 409}:
        _expect(r1, {200, 201}, context="POST /api/programs/ (admin1)")

    r2 = c2.post("/api/programs/", json={"code": code, "name": f"{code} (A2)"})
    if r2.status_code not in {200, 201, 409}:
        _expect(r2, {200, 201}, context="POST /api/programs/ (admin2)")

    rows1 = _expect(c1.get("/api/programs/"), {200}, context="GET /api/programs/ (admin1)")
    rows2 = _expect(c2.get("/api/programs/"), {200}, context="GET /api/programs/ (admin2)")

    if not isinstance(rows1, list) or not isinstance(rows2, list):
        raise SystemExit(f"FAIL unexpected list payloads admin1={rows1!r} admin2={rows2!r}")

    p1 = next((p for p in rows1 if isinstance(p, dict) and p.get("code") == code), None)
    p2 = next((p for p in rows2 if isinstance(p, dict) and p.get("code") == code), None)
    if not p1 or not p2:
        raise SystemExit(f"FAIL program not visible in tenant list p1={p1!r} p2={p2!r}")

    if p1.get("id") == p2.get("id"):
        raise SystemExit("FAIL program ids match across tenants")

    # Cross-tenant mutation by id must be blocked.
    _expect(
        c2.patch(f"/api/programs/{p1['id']}", json={"name": "HACK"}),
        {404},
        context="PATCH /api/programs/{id} cross-tenant",
    )

    print("OK seeded-admin tenant isolation")
    print(" admin1 program:", p1)
    print(" admin2 program:", p2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
