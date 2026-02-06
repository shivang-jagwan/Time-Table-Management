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


def _to_code_set(rows: Any, *, code_key: str = "code") -> set[str]:
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            code = row.get(code_key)
            if isinstance(code, str) and code:
                out.add(code)
    return out


def _report_overlap(*, label: str, admin1: set[str], admin2: set[str]) -> None:
    overlap = admin1 & admin2
    print(f" {label}: admin1={len(admin1)} admin2={len(admin2)} overlap={len(overlap)}")


def _to_id_set(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    out: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            rid = row.get("id")
            if isinstance(rid, str) and rid:
                out.add(rid)
    return out


def _report_shared_ids(*, label: str, admin1_ids: set[str], admin2_ids: set[str]) -> None:
    shared = admin1_ids & admin2_ids
    print(f" {label}: admin1={len(admin1_ids)} admin2={len(admin2_ids)} shared_ids={len(shared)}")


def main() -> None:
    c1 = TestClient(app)
    c2 = TestClient(app)

    _login(c1, username="DeepaliDon", password="Deepalidon@always")
    _login(c2, username="chotapaaji", password="chotasardar")

    code = "ISO_TENANT"
    teacher_code = "T_ISO_TENANT"
    room_code = "R_ISO_TENANT"

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

    # Teachers: same code allowed, different IDs.
    tr1 = c1.post("/api/teachers/", json={"code": teacher_code, "full_name": f"{teacher_code} (A1)"})
    if tr1.status_code not in {200, 201, 409}:
        _expect(tr1, {200, 201}, context="POST /api/teachers/ (admin1)")
    tr2 = c2.post("/api/teachers/", json={"code": teacher_code, "full_name": f"{teacher_code} (A2)"})
    if tr2.status_code not in {200, 201, 409}:
        _expect(tr2, {200, 201}, context="POST /api/teachers/ (admin2)")

    trows1 = _expect(c1.get("/api/teachers/"), {200}, context="GET /api/teachers/ (admin1)")
    trows2 = _expect(c2.get("/api/teachers/"), {200}, context="GET /api/teachers/ (admin2)")
    if not isinstance(trows1, list) or not isinstance(trows2, list):
        raise SystemExit(f"FAIL unexpected teachers payloads admin1={trows1!r} admin2={trows2!r}")
    t1 = next((t for t in trows1 if isinstance(t, dict) and t.get("code") == teacher_code), None)
    t2 = next((t for t in trows2 if isinstance(t, dict) and t.get("code") == teacher_code), None)
    if not t1 or not t2:
        raise SystemExit(f"FAIL teacher not visible in tenant list t1={t1!r} t2={t2!r}")
    if t1.get("id") == t2.get("id"):
        raise SystemExit("FAIL teacher ids match across tenants")
    _expect(
        c2.patch(f"/api/teachers/{t1['id']}", json={"full_name": "HACK"}),
        {404},
        context="PATCH /api/teachers/{id} cross-tenant",
    )

    # Rooms: same code allowed, different IDs.
    room_payload1 = {
        "code": room_code,
        "name": f"{room_code} (A1)",
        "room_type": "CLASSROOM",
        "capacity": 60,
        "is_active": True,
        "is_special": False,
        "special_note": None,
    }
    room_payload2 = {**room_payload1, "name": f"{room_code} (A2)"}
    rr1 = c1.post("/api/rooms/", json=room_payload1)
    if rr1.status_code not in {200, 201, 409}:
        _expect(rr1, {200, 201}, context="POST /api/rooms/ (admin1)")
    rr2 = c2.post("/api/rooms/", json=room_payload2)
    if rr2.status_code not in {200, 201, 409}:
        _expect(rr2, {200, 201}, context="POST /api/rooms/ (admin2)")

    rrows1 = _expect(c1.get("/api/rooms/"), {200}, context="GET /api/rooms/ (admin1)")
    rrows2 = _expect(c2.get("/api/rooms/"), {200}, context="GET /api/rooms/ (admin2)")
    if not isinstance(rrows1, list) or not isinstance(rrows2, list):
        raise SystemExit(f"FAIL unexpected rooms payloads admin1={rrows1!r} admin2={rrows2!r}")
    rm1 = next((r for r in rrows1 if isinstance(r, dict) and r.get("code") == room_code), None)
    rm2 = next((r for r in rrows2 if isinstance(r, dict) and r.get("code") == room_code), None)
    if not rm1 or not rm2:
        raise SystemExit(f"FAIL room not visible in tenant list rm1={rm1!r} rm2={rm2!r}")
    if rm1.get("id") == rm2.get("id"):
        raise SystemExit("FAIL room ids match across tenants")
    _expect(
        c2.patch(f"/api/rooms/{rm1['id']}", json={"name": "HACK"}),
        {404},
        context="PATCH /api/rooms/{id} cross-tenant",
    )

    # Solver runs: must not be visible cross-tenant.
    gen1 = _expect(
        c1.post("/api/solver/generate-global", json={"program_code": code, "seed": 1}),
        {200},
        context="POST /api/solver/generate-global (admin1)",
    )
    gen2 = _expect(
        c2.post("/api/solver/generate-global", json={"program_code": code, "seed": 2}),
        {200},
        context="POST /api/solver/generate-global (admin2)",
    )
    run1 = gen1.get("run_id") if isinstance(gen1, dict) else None
    run2 = gen2.get("run_id") if isinstance(gen2, dict) else None
    if not run1 or not run2:
        raise SystemExit(f"FAIL expected run_ids from generate-global: admin1={gen1!r} admin2={gen2!r}")

    runs1 = _expect(c1.get("/api/solver/runs", params={"limit": 50}), {200}, context="GET /api/solver/runs (admin1)")
    runs2 = _expect(c2.get("/api/solver/runs", params={"limit": 50}), {200}, context="GET /api/solver/runs (admin2)")
    ids1 = {r.get("id") for r in runs1.get("runs", [])} if isinstance(runs1, dict) else set()
    ids2 = {r.get("id") for r in runs2.get("runs", [])} if isinstance(runs2, dict) else set()
    if run1 not in ids1:
        raise SystemExit(f"FAIL admin1 cannot see its own run {run1}")
    if run2 not in ids2:
        raise SystemExit(f"FAIL admin2 cannot see its own run {run2}")
    if run1 in ids2:
        raise SystemExit(f"FAIL admin2 can see admin1 run {run1}")
    if run2 in ids1:
        raise SystemExit(f"FAIL admin1 can see admin2 run {run2}")
    _expect(c2.get(f"/api/solver/runs/{run1}"), {404}, context="GET /api/solver/runs/{id} cross-tenant")

    # Human-friendly report (no UUID IDs).
    # Codes can overlap by design (same code in different tenants). IDs must never overlap.
    program_ids1 = _to_id_set(rows1)
    program_ids2 = _to_id_set(rows2)
    teacher_ids1 = _to_id_set(trows1)
    teacher_ids2 = _to_id_set(trows2)
    room_ids1 = _to_id_set(rrows1)
    room_ids2 = _to_id_set(rrows2)

    print("OK tenant isolation (DeepaliDon vs chotapaaji)")
    print(" Created in both tenants:")
    print(f"  - program code: {code}")
    print(f"  - teacher code: {teacher_code}")
    print(f"  - room code: {room_code}")
    print(" Shared record IDs across tenants (must be 0):")
    _report_shared_ids(label="programs", admin1_ids=program_ids1, admin2_ids=program_ids2)
    _report_shared_ids(label="teachers", admin1_ids=teacher_ids1, admin2_ids=teacher_ids2)
    _report_shared_ids(label="rooms", admin1_ids=room_ids1, admin2_ids=room_ids2)
    print(" Cross-tenant access checks:")
    print("  - programs: PATCH by other-tenant id => 404")
    print("  - teachers: PATCH by other-tenant id => 404")
    print("  - rooms: PATCH by other-tenant id => 404")
    print("  - solver runs: list is tenant-scoped; other-tenant run detail => 404")

    # Keep these local values to ensure the solver checks stay meaningful,
    # but do not print them to avoid confusion about UUIDs.
    _ = (p1, p2, t1, t2, rm1, rm2, run1, run2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
