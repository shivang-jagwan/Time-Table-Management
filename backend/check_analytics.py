#!/usr/bin/env python3
import json
from sqlalchemy import select
from core.db import SessionLocal
from models.timetable_run import TimetableRun

db = SessionLocal()
try:
    run = db.execute(select(TimetableRun).order_by(TimetableRun.created_at.desc()).limit(1)).scalars().first()
    
    if run and run.analytics_dict:
        analytics = run.analytics_dict
        print("[ANALYTICS DATA]")
        print(f"Run ID: {run.id}")
        print(f"Solver Status: {analytics.get('cp_sat_status')}")
        print(f"Variables: {analytics.get('variables_created')}")
        print(f"Constraints: {analytics.get('constraints_created')}")
        print(f"Objective: {analytics.get('total_objective_value')}")
        print(f"Coverage: {analytics.get('coverage_percentage')}%")
        print(f"Room Util: {analytics.get('room_utilization_percentage')}%")
        print(f"Entries: {analytics.get('entries_written')}")
        print()
        print("FULL ANALYTICS JSON:")
        print(json.dumps(analytics, indent=2))
    else:
        print("No analytics found")
finally:
    db.close()
