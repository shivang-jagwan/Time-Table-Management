#!/usr/bin/env python3
"""Show and delete recent runs for debugging"""

import sys
from sqlalchemy import select, desc

sys.path.insert(0, '/d/timetable/backend')

from core.database import SessionLocal
from models import User, TimetableRun, TimetableEntry

def main():
    db = SessionLocal()
    try:
        # Find shivang123 user
        user_query = select(User).where(User.username == "shivang123")
        user = db.execute(user_query).scalar_one_or_none()
        
        if not user:
            print("❌ User shivang123 not found")
            return
        
        print(f"✅ Found user: {user.username} (ID: {user.id})\n")
        
        # Get ALL recent runs (regardless of tenant)
        runs_query = select(TimetableRun).order_by(desc(TimetableRun.created_at)).limit(10)
        runs = db.execute(runs_query).scalars().all()
        
        if not runs:
            print("ℹ️  No runs found at all")
            return
        
        print(f"📊 Last {len(runs)} runs (any tenant):")
        for i, run in enumerate(runs, 1):
            tenant_str = str(run.tenant_id) if run.tenant_id else "SHARED"
            is_this_user = "👈 THIS USER" if run.tenant_id == user.id else ""
            print(f"   {i}. {run.id}")
            print(f"      Status: {run.status} | Tenant: {tenant_str} {is_this_user}")
            print(f"      Created: {run.created_at}")
        
        # Find runs for this user specifically
        user_runs = [r for r in runs if r.tenant_id == user.id]
        
        if not user_runs:
            print(f"\n⚠️  No runs found for user {user.username}")
            print("    All recent runs are SHARED (tenant_id=NULL)")
            print("\n❓ Deleting the most recent SHARED run instead...")
            if runs:
                latest = runs[0]
                print(f"\n   Latest shared run: {latest.id}")
                print(f"   Status: {latest.status}")
                
                # Get entries
                entries = db.execute(
                    select(TimetableEntry)
                    .where(TimetableEntry.run_id == latest.id)
                ).scalars().all()
                
                print(f"   Entries: {len(entries)}")
                
                # Delete
                for entry in entries:
                    db.delete(entry)
                db.delete(latest)
                db.commit()
                print("\n✅ Deleted!")
        else:
            latest_user_run = user_runs[0]
            print(f"\n✅ Deleting user's latest run: {latest_user_run.id}")
            
            # Count entries
            entries = db.execute(
                select(TimetableEntry)
                .where(TimetableEntry.run_id == latest_user_run.id)
            ).scalars().all()
            
            print(f"   Entries to delete: {len(entries)}")
            
            # Delete
            for entry in entries:
                db.delete(entry)
            db.delete(latest_user_run)
            db.commit()
            print("   ✅ Deleted!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    main()
