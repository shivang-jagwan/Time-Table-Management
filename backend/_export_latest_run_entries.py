import os
import json
import csv
from datetime import datetime
from typing import Any, Dict, List

import httpx


BASE_URL = os.environ.get("TT_API_BASE_URL", "http://localhost:8000")
USERNAME = os.environ.get("TT_USERNAME", "DeepaliDon")
PASSWORD = os.environ.get("TT_PASSWORD", "Deepalidon@always")


def _signup(client: httpx.Client) -> None:
    resp = client.post(
        f"{BASE_URL}/api/auth/signup",
        json={"username": USERNAME, "password": PASSWORD, "full_name": USERNAME, "email": f"{USERNAME}@example.com"},
    )
    # Signup may be disabled or user may already exist; ignore 4xx
    if resp.status_code >= 500:
        resp.raise_for_status()


def _login(client: httpx.Client) -> None:
    resp = client.post(f"{BASE_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    if resp.status_code == 401:
        # Try to signup then login again
        _signup(client)
        resp = client.post(f"{BASE_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    resp.raise_for_status()


def _list_runs(client: httpx.Client) -> List[Dict[str, Any]]:
    resp = client.get(f"{BASE_URL}/api/solver/runs")
    resp.raise_for_status()
    data = resp.json()
    # Expecting a structure like {"runs": [...]}
    runs = data.get("runs") if isinstance(data, dict) else data
    if not isinstance(runs, list):
        raise RuntimeError("Unexpected runs response format")
    return runs


def _pick_latest_run(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Prefer OPTIMAL, else take most recent by created_at if available
    optimal = [r for r in runs if r.get("status") == "OPTIMAL"]
    if optimal:
        # Sort by created_at desc if available
        optimal.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return optimal[0]
    # Fallback: sort by created_at
    runs.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return runs[0]


def _get_entries(client: httpx.Client, run_id: str) -> List[Dict[str, Any]]:
    resp = client.get(f"{BASE_URL}/api/solver/runs/{run_id}/entries")
    resp.raise_for_status()
    data = resp.json()
    # Expecting structure like {"entries": [...]} or a plain list
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise RuntimeError("Unexpected entries response format")
    return entries


def _export_json(entries: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def _export_csv(entries: List[Dict[str, Any]], path: str) -> None:
    # Collect all keys present across entries for a flexible header
    keys = set()
    for e in entries:
        keys.update(e.keys())
    header = sorted(keys)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for e in entries:
            writer.writerow(e)


def main() -> None:
    outputs_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    with httpx.Client(follow_redirects=True) as client:
        _login(client)
        runs = _list_runs(client)
        if not runs:
            print("No runs found to export.")
            return
        chosen = _pick_latest_run(runs)
        run_id = chosen.get("run_id") or chosen.get("id")
        if not run_id:
            raise RuntimeError("Run identifier not found in run object")
        entries = _get_entries(client, run_id)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(outputs_dir, f"run_{run_id}_{ts}")
        json_path = f"{base}_entries.json"
        csv_path = f"{base}_entries.csv"
        _export_json(entries, json_path)
        _export_csv(entries, csv_path)
        print({
            "run_id": run_id,
            "entries_count": len(entries),
            "json_path": json_path,
            "csv_path": csv_path,
        })


if __name__ == "__main__":
    main()
