from __future__ import annotations

import getpass
import json
import os
from typing import Any

import httpx


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for k, v in obj.items():
            if str(k).lower() in {"password", "token", "access_token", "refresh_token"}:
                redacted[k] = "<redacted>"
            else:
                redacted[k] = _redact(v)
        return redacted
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def main() -> None:
    base = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
    username = os.environ.get("USERNAME") or input("Username: ").strip()
    password = os.environ.get("PASSWORD") or getpass.getpass("Password: ")

    with httpx.Client(base_url=base, follow_redirects=True) as client:
        r = client.post("/api/auth/login", json={"username": username, "password": password}, timeout=30)
        payload = _safe_json(r.text)
        if payload is not None:
            print("login", r.status_code, _redact(payload))
        else:
            print("login", r.status_code, (r.text[:500] + "...") if len(r.text) > 500 else r.text)

        r2 = client.get("/api/auth/me", timeout=30)
        payload2 = _safe_json(r2.text)
        if payload2 is not None:
            print("me", r2.status_code, _redact(payload2))
        else:
            print("me", r2.status_code, (r2.text[:500] + "...") if len(r2.text) > 500 else r2.text)

        if os.environ.get("DO_SOLVE_GLOBAL", "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            program_code = os.environ.get("PROGRAM_CODE", "CSE")
            max_time_seconds = float(os.environ.get("MAX_TIME_SECONDS", "30"))
            relax_teacher_load_limits = os.environ.get("RELAX_TEACHER_LOAD_LIMITS", "").strip() in {
                "1",
                "true",
                "TRUE",
                "yes",
                "YES",
            }
            require_optimal = os.environ.get("REQUIRE_OPTIMAL", "1").strip() in {
                "1",
                "true",
                "TRUE",
                "yes",
                "YES",
            }

            solve_payload = {
                "program_code": program_code,
                "max_time_seconds": max_time_seconds,
                "relax_teacher_load_limits": relax_teacher_load_limits,
                "require_optimal": require_optimal,
            }
            r3 = client.post(
                "/api/solver/solve-global",
                json=solve_payload,
                timeout=max(60, int(max_time_seconds) + 30),
            )
            payload3 = _safe_json(r3.text)
            if payload3 is not None:
                print("solve-global", r3.status_code, _redact(payload3))
            else:
                print("solve-global", r3.status_code, (r3.text[:2000] + "...") if len(r3.text) > 2000 else r3.text)


if __name__ == "__main__":
    main()
