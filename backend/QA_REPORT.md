# Timetable Solver QA Report (Global 3 Years)

Date: 2026-02-05
Environment: Windows, FastAPI TestClient (no external server required)

## Overview
- Objective: Stress-test global solve across 3 years under tight constraints with electives, combined classes, and special/fixed locks.
- Key addition (2026-02-05): **Hard section compactness constraint** — for any section within a single day, the gap between two scheduled classes must not exceed **3 consecutive empty slots** (1 slot = 1 hour).
- Secondary objective (soft): minimize internal gaps per section per day (keeps schedules compact when multiple solutions exist).
- Status: Harness runs successfully end-to-end; feasibility depends heavily on teacher daily load caps and locked events.

## Seed Configuration
- Program: CSE; Years: 1–3; Sections per year: 6 (A–F).
- Rooms: CR1, CR2 (CLASSROOM), LT1 (LT), LAB1 (LAB), SR1 (SPECIAL).
- Subjects per year: T1, T2, T3 (4 sessions/week each), LAB (1 block × 2 slots).
- Teachers: T1–T8 (max_per_day=6, max_per_week=36, off-day randomized), L1–L2 (max_per_day=4, max_per_week=20), CS1 (combined specialist, max_per_day=6, max_per_week=36).
- Combined groups: Per year, Y{year}-T3 combined for first three sections.
- Special/Fixed locks: 5 special allotments in SR1; 5 fixed entries; 1 intentional teacher-slot conflict.

## Capacity Analysis Summary
- Teacher limits: Increased `max_per_day` via harness fallback (DB update) for theory to 9 and lab to 5; off-day disabled for feasibility testing.
- Combined groups: Attribution fixed to count once per group for shared teacher; analyzer now filters combined groups to selected sections to avoid cross-year leakage.
- Rooms/sections: No room scarcity under current configuration; lab contiguity satisfied; special room usage present only via special allotments.

## Solver Outcomes
- Seeds tested by harness: 1, 2, 42, 99.
- Baseline (tight constraints + locks): may be **INFEASIBLE** depending on teacher daily load caps and locked events.
- Feasibility demonstration (capacity widened + locks skipped + teacher load limits relaxed): **FEASIBLE** for all tested seeds, with the new section max-gap constraint satisfied.

### Feasible run (observed)
Configuration used:
- `TT_SKIP_SPECIAL=1`, `TT_SKIP_FIXED=1`
- `TT_MORE_ROOMS=1`, `TT_LONGER_DAY=1`, `TT_MORE_DAYS=1`
- `TT_RELAX=1` (teacher load limits disabled)

Observed results (new section-gap metrics in `solver_stats`):
- Seed 1: `section_gap_max_empty_slots=2`, `section_gap_avg_empty_slots=0.0759`, `section_internal_gap_slots=11`
- Seed 2: `section_gap_max_empty_slots=3`, `section_gap_avg_empty_slots=0.3446`, `section_internal_gap_slots=51`
- Seed 42: `section_gap_max_empty_slots=3`, `section_gap_avg_empty_slots=0.3194`, `section_internal_gap_slots=46`
- Seed 99: `section_gap_max_empty_slots=2`, `section_gap_avg_empty_slots=0.1103`, `section_internal_gap_slots=16`

### New solver stats fields
When a run is FEASIBLE/OPTIMAL, solver now reports section gap metrics in `solver_stats`:
- `section_gap_max_empty_slots`
- `section_gap_avg_empty_slots`
- `section_internal_gap_slots`

## Recommendations
- If the harness reports `TEACHER_DAILY_LOAD_VIOLATION`, relax teacher caps (e.g., increase `max_per_day`, increase working days, or reduce locked events) before attributing infeasibility to section-gap compactness.
- Once FEASIBLE/OPTIMAL, validate the new constraint via `solver_stats.section_gap_max_empty_slots <= 3`.
- Keep section windows and section breaks realistic; excessive breaks can make the max-gap constraint infeasible.
- When using `TT_RELAX=1`, treat results as a feasibility/constraint-validation run (teacher load caps are intentionally disabled).

## Repro Steps (PowerShell)
```powershell
# From workspace root
# Run stress harness with TestClient (no server needed), using capacity flags
$env:TT_COMBINED_COUNT="2"; $env:TT_COMBINED_YEARS="1"; $env:TT_COMBINED_TEACHER_Y1="T8"; `
$env:TT_INCREASE_MPD="1"; $env:TT_MPD="9"; $env:TT_LAB_MPD="5"; `
$env:TT_LONGER_DAY="1"; $env:TT_MORE_ROOMS="1"; $env:TT_DISABLE_OFFDAY="1"; $env:TT_NO_PATCH="0"; `
D:\gpt\backend\.venv\Scripts\python.exe D:\gpt\backend\_qa_stress_test.py

# Feasible demonstration run (skips locks, widens capacity, relaxes teacher load limits)
$env:TT_INCREASE_MPD="1"; $env:TT_MPD="12"; $env:TT_LAB_MPD="8"; $env:TT_DISABLE_OFFDAY="1"; `
$env:TT_SKIP_SPECIAL="1"; $env:TT_SKIP_FIXED="1"; $env:TT_MORE_ROOMS="1"; $env:TT_LONGER_DAY="1"; $env:TT_MORE_DAYS="1"; $env:TT_RELAX="1"; `
D:\gpt\backend\.venv\Scripts\python.exe D:\gpt\backend\_qa_stress_test.py

# Or start server and use UI/API manually
D:\gpt\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

## Artifacts
- Stress harness: backend/_qa_stress_test.py
- Capacity Analyzer: backend/solver/capacity_analyzer.py (combined-group filter applied)
- Solver diagnostics: backend/solver/solver_diagnostics.py (combined-group attribution fix)
- Solver routes: backend/api/routes/solver.py (debug_capacity_mode, smart_relaxation integration)
- Schemas: backend/schemas/solver.py (request/response flags)

## Next Work
- Add Bottleneck Reporting Engine for granular shortages.
- Tune objective to minimize teacher load imbalance and peak concurrency.
- Provide guided auto-relaxation trials for exploratory analysis.
