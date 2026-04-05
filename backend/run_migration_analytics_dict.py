#!/usr/bin/env python3
"""Run database migration to add analytics_dict column."""

from sqlalchemy import text
from core.db import ENGINE

def run_migration():
    """Add analytics_dict column to timetable_runs table."""
    
    migration_sql = """
    ALTER TABLE timetable_runs
    ADD COLUMN analytics_dict JSONB NULL;
    """
    
    try:
        with ENGINE.begin() as conn:
            conn.execute(text(migration_sql))
        print("✅ Migration successful: analytics_dict column added to timetable_runs")
        return True
    except Exception as e:
        print(f"⚠️  Migration note: {e}")
        # Column might already exist, which is fine
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("   (Column likely already exists - that's OK)")
            return True
        raise

if __name__ == "__main__":
    run_migration()
