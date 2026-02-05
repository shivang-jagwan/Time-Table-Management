from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient
import bcrypt
from sqlalchemy import select, text

from core.config import settings
from core.db import SessionLocal
from main import app
from models.tenant import Tenant
from models.user import User


@dataclass(frozen=True)
class AdminCreds:
    username: str
    password: str
    tenant: str | None = None


def _env(name: str) -> str | None:
    v = os.environ.get(name)
    if v is None:
        return None
    v = v.strip()
    return v or None


def _get_admin_creds() -> tuple[AdminCreds, AdminCreds]:
    # Prefer explicit env vars so this script works with any credentials.
    a1u = _env("SMOKE_ADMIN1_USERNAME") or _env("ADMIN1_USERNAME")
    a1p = _env("SMOKE_ADMIN1_PASSWORD") or _env("ADMIN1_PASSWORD")
    a2u = _env("SMOKE_ADMIN2_USERNAME") or _env("ADMIN2_USERNAME")
    a2p = _env("SMOKE_ADMIN2_PASSWORD") or _env("ADMIN2_PASSWORD")

    if a1u and a1p and a2u and a2p:
        return AdminCreds(a1u, a1p, None), AdminCreds(a2u, a2p, None)

    # Fallback defaults match migrations/003_seed_two_admins.py.
    # If these users don't exist in your DB, login will fail with a helpful error.
    return AdminCreds("DeepaliDon", "Deepalidon@always", None), AdminCreds("chotapaaji", "chotasardar", None)


def _json(resp) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text


def _expect(resp, ok_codes: set[int], *, context: str) -> Any:
    payload = _json(resp)
    if resp.status_code not in ok_codes:
        raise SystemExit(f"FAIL {context}: {resp.status_code} {payload}")
    return payload


def _login(client: TestClient, creds: AdminCreds) -> None:
    payload: dict[str, Any] = {"username": creds.username, "password": creds.password}
    if creds.tenant:
        payload["tenant"] = creds.tenant
    resp = client.post("/api/auth/login", json=payload)
    if resp.status_code >= 400:
        payload = _json(resp)
        raise SystemExit(
            "FAIL /api/auth/login for user="
            + repr(creds.username)
            + f": {resp.status_code} {payload}\n\n"
            + "If these users don't exist yet, run:\n"
            + "  python -m migrations.003_seed_two_admins --yes\n"
        )


def _hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def _ensure_tenant_and_admin(*, slug: str, name: str, username: str, password: str) -> None:
    with SessionLocal() as db:
        t = db.execute(select(Tenant).where(Tenant.slug == slug)).scalars().first()
        if t is None:
            t = Tenant(slug=slug, name=name)
            db.add(t)
            db.commit()
            db.refresh(t)

        u = (
            db.execute(
                select(User)
                .where(User.tenant_id == t.id)
                .where(User.username.ilike(username))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if u is None:
            pw_hash = _hash_password(password)

            has_name = (
                db.execute(
                    text(
                        """
                        select 1
                        from information_schema.columns
                        where table_schema='public'
                          and table_name='users'
                          and column_name='name'
                        limit 1
                        """.strip()
                    )
                ).first()
                is not None
            )

            if has_name:
                db.execute(
                    text(
                        """
                        insert into users (tenant_id, name, username, password_hash, role, is_active)
                        values (:tenant_id, :name, :username, :password_hash, 'ADMIN', true)
                        """.strip()
                    ),
                    {
                        "tenant_id": str(t.id),
                        "name": username,
                        "username": username,
                        "password_hash": pw_hash,
                    },
                )
            else:
                db.add(
                    User(
                        tenant_id=t.id,
                        username=username,
                        password_hash=pw_hash,
                        role="ADMIN",
                        is_active=True,
                    )
                )
            db.commit()


def _ensure_program(client: TestClient, *, code: str, name: str) -> dict[str, Any]:
    create = client.post("/api/programs/", json={"code": code, "name": name})
    if create.status_code in {200, 201}:
        return _expect(create, {200, 201}, context="POST /api/programs/")

    if create.status_code != 409:
        _expect(create, {200, 201}, context="POST /api/programs/")

    # Already exists in this tenant — return the existing row.
    rows = _expect(client.get("/api/programs/"), {200}, context="GET /api/programs/")
    if not isinstance(rows, list):
        raise SystemExit(f"FAIL GET /api/programs/: unexpected payload {rows!r}")
    for r in rows:
        if isinstance(r, dict) and r.get("code") == code:
            return r
    raise SystemExit(
        "FAIL program create returned 409 but program not found in tenant list. "
        "If you're in per-user mode and this happens for admin2, migrations (026) may not be applied (partial unique indexes)."
    )


def _ensure_teacher(client: TestClient, *, code: str, full_name: str) -> dict[str, Any]:
    create = client.post("/api/teachers/", json={"code": code, "full_name": full_name})
    if create.status_code in {200, 201}:
        return _expect(create, {200, 201}, context="POST /api/teachers/")

    if create.status_code != 409:
        _expect(create, {200, 201}, context="POST /api/teachers/")

    rows = _expect(client.get("/api/teachers/"), {200}, context="GET /api/teachers/")
    if not isinstance(rows, list):
        raise SystemExit(f"FAIL GET /api/teachers/: unexpected payload {rows!r}")
    for r in rows:
        if isinstance(r, dict) and r.get("code") == code:
            return r
    raise SystemExit("FAIL teacher create returned 409 but teacher not found in tenant list")


def _ensure_room(client: TestClient, *, code: str, name: str) -> dict[str, Any]:
    payload = {
        "code": code,
        "name": name,
        "room_type": "CLASSROOM",
        "capacity": 60,
        "is_active": True,
        "is_special": False,
        "special_note": None,
    }
    create = client.post("/api/rooms/", json=payload)
    if create.status_code in {200, 201}:
        return _expect(create, {200, 201}, context="POST /api/rooms/")

    if create.status_code != 409:
        _expect(create, {200, 201}, context="POST /api/rooms/")

    rows = _expect(client.get("/api/rooms/"), {200}, context="GET /api/rooms/")
    if not isinstance(rows, list):
        raise SystemExit(f"FAIL GET /api/rooms/: unexpected payload {rows!r}")
    for r in rows:
        if isinstance(r, dict) and r.get("code") == code:
            return r
    raise SystemExit("FAIL room create returned 409 but room not found in tenant list")


def _assert_not_visible(*, client: TestClient, url: str, method: str = "GET", json: dict | None = None) -> None:
    if method == "GET":
        resp = client.get(url)
    elif method == "PATCH":
        resp = client.patch(url, json=json)
    elif method == "DELETE":
        resp = client.delete(url)
    else:
        raise ValueError(f"Unsupported method {method}")

    if resp.status_code != 404:
        raise SystemExit(f"FAIL expected 404 for cross-tenant access {method} {url}: {resp.status_code} {_json(resp)}")


def main() -> None:
    mode = (settings.tenant_mode or "shared").strip().lower()
    if mode not in {"per_user", "per_tenant"}:
        raise SystemExit(
            "This smoke test is for tenant isolation. Set TENANT_MODE=per_user or TENANT_MODE=per_tenant in backend/.env and restart. "
            f"Current tenant_mode={settings.tenant_mode!r}"
        )

    admin1, admin2 = _get_admin_creds()

    # In strict per-tenant mode, ensure two tenants + two admin users exist.
    if mode == "per_tenant":
        t1 = os.environ.get("SMOKE_TENANT1", "smoke-a")
        t2 = os.environ.get("SMOKE_TENANT2", "smoke-b")
        u1 = os.environ.get("SMOKE_TENANT1_ADMIN_USERNAME", "smokeadmin1")
        p1 = os.environ.get("SMOKE_TENANT1_ADMIN_PASSWORD", "SmokeAdmin1@123")
        u2 = os.environ.get("SMOKE_TENANT2_ADMIN_USERNAME", "smokeadmin2")
        p2 = os.environ.get("SMOKE_TENANT2_ADMIN_PASSWORD", "SmokeAdmin2@123")

        _ensure_tenant_and_admin(slug=t1, name=f"Smoke Tenant {t1}", username=u1, password=p1)
        _ensure_tenant_and_admin(slug=t2, name=f"Smoke Tenant {t2}", username=u2, password=p2)

        admin1 = AdminCreds(username=u1, password=p1, tenant=t1)
        admin2 = AdminCreds(username=u2, password=p2, tenant=t2)

    c1 = TestClient(app)
    c2 = TestClient(app)

    _login(c1, admin1)
    _login(c2, admin2)

    # Use the same codes for both tenants — this is the critical uniqueness/isolation check.
    program_code = os.environ.get("SMOKE_PROGRAM_CODE", "TENANT_SMOKE")
    teacher_code = os.environ.get("SMOKE_TEACHER_CODE", "T_TENANT_SMOKE")
    room_code = os.environ.get("SMOKE_ROOM_CODE", "R_TENANT_SMOKE")

    p1 = _ensure_program(c1, code=program_code, name=f"{program_code} (A1)")
    p2 = _ensure_program(c2, code=program_code, name=f"{program_code} (A2)")
    if p1.get("id") == p2.get("id"):
        raise SystemExit("FAIL programs share the same id across tenants")

    t1 = _ensure_teacher(c1, code=teacher_code, full_name=f"Teacher {teacher_code} (A1)")
    t2 = _ensure_teacher(c2, code=teacher_code, full_name=f"Teacher {teacher_code} (A2)")
    if t1.get("id") == t2.get("id"):
        raise SystemExit("FAIL teachers share the same id across tenants")

    r1 = _ensure_room(c1, code=room_code, name=f"Room {room_code} (A1)")
    r2 = _ensure_room(c2, code=room_code, name=f"Room {room_code} (A2)")
    if r1.get("id") == r2.get("id"):
        raise SystemExit("FAIL rooms share the same id across tenants")

    # Cross-tenant object access by ID must be blocked.
    _assert_not_visible(client=c2, url=f"/api/programs/{p1['id']}", method="PATCH", json={"name": "HACK"})
    _assert_not_visible(client=c2, url=f"/api/teachers/{t1['id']}", method="PATCH", json={"full_name": "HACK"})
    _assert_not_visible(client=c2, url=f"/api/rooms/{r1['id']}", method="PATCH", json={"name": "HACK"})

    # Solver runs must be tenant-isolated too.
    # Use generate-global (no academic year required). Even if validation fails (e.g., no sections), it must create a run.
    gen1 = _expect(
        c1.post("/api/solver/generate-global", json={"program_code": program_code, "seed": 1}),
        {200},
        context="POST /api/solver/generate-global (admin1)",
    )
    gen2 = _expect(
        c2.post("/api/solver/generate-global", json={"program_code": program_code, "seed": 2}),
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

    # Cross-tenant run detail must be hidden.
    _assert_not_visible(client=c2, url=f"/api/solver/runs/{run1}", method="GET")

    print("OK tenant isolation smoke:")
    print(f"  admin1 program_id={p1['id']} teacher_id={t1['id']} room_id={r1['id']} run_id={run1}")
    print(f"  admin2 program_id={p2['id']} teacher_id={t2['id']} room_id={r2['id']} run_id={run2}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
