from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from main import app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("USERNAME", "shivang123"))
    parser.add_argument("--password", default=os.environ.get("PASSWORD", "Shivang@GEHU123"))
    parser.add_argument("--program-code", default=os.environ.get("PROGRAM_CODE", "CSE"))
    parser.add_argument("--max-time-seconds", type=float, default=60.0)
    parser.add_argument("--require-optimal", action="store_true")
    parser.add_argument("--relax-teacher-load-limits", action="store_true")
    return parser.parse_args()


def _safe_json(resp) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def _ensure_ok(resp, context: str) -> dict[str, Any]:
    payload = _safe_json(resp)
    if resp.status_code >= 400:
        raise RuntimeError(f"{context} failed: HTTP {resp.status_code} payload={payload}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} returned non-object payload: {payload}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(__file__).resolve().parent
    out_dir = root / "outputs"

    years = [2, 3]
    summary: dict[str, Any] = {
        "program_code": args.program_code,
        "years": {},
    }

    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": args.username, "password": args.password},
        )
        login_payload = _safe_json(login)
        if login.status_code >= 400:
            raise RuntimeError(f"login failed: HTTP {login.status_code} payload={login_payload}")

        for year in years:
            solve_payload = {
                "program_code": args.program_code,
                "academic_year_number": year,
                "max_time_seconds": float(args.max_time_seconds),
                "relax_teacher_load_limits": bool(args.relax_teacher_load_limits),
                "require_optimal": bool(args.require_optimal),
            }
            solve_resp = client.post("/api/solver/solve", json=solve_payload)
            solve = _ensure_ok(solve_resp, f"solve year {year}")

            run_id = solve.get("run_id")
            status = solve.get("status")
            entries_written = int(solve.get("entries_written") or 0)

            if not run_id:
                raise RuntimeError(f"solve year {year} returned no run_id: {solve}")
            if status not in {"FEASIBLE", "SUBOPTIMAL", "OPTIMAL"}:
                conflicts = solve.get("conflicts")
                raise RuntimeError(
                    f"solve year {year} did not produce solution status. status={status} conflicts={conflicts}"
                )

            entries_resp = client.get(f"/api/solver/runs/{run_id}/entries")
            entries_payload = _ensure_ok(entries_resp, f"entries fetch year {year}")
            entries = entries_payload.get("entries")
            if not isinstance(entries, list):
                raise RuntimeError(f"entries payload malformed for year {year}: {entries_payload}")

            run_resp = client.get(f"/api/solver/runs/{run_id}")
            run_payload = _ensure_ok(run_resp, f"run detail year {year}")

            year_out = {
                "solve_request": solve_payload,
                "solve_response": solve,
                "run": run_payload,
                "entries_total_fetched": len(entries),
                "entries": entries,
            }
            out_path = out_dir / f"timetable_year{year}_{run_id}.json"
            _write_json(out_path, year_out)

            summary["years"][str(year)] = {
                "run_id": run_id,
                "status": status,
                "entries_written": entries_written,
                "entries_fetched": len(entries),
                "output_file": str(out_path),
            }

            print(
                f"YEAR {year}: status={status} run_id={run_id} "
                f"entries_written={entries_written} entries_fetched={len(entries)}"
            )

    summary_path = out_dir / "timetable_year2_year3_summary.json"
    _write_json(summary_path, summary)
    print(f"SUMMARY_FILE={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
