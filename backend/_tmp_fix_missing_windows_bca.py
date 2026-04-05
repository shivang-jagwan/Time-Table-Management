import uuid
from sqlalchemy import select

from core.database import SessionLocal
from models.user import User
from models.timetable_run import TimetableRun
from models.program import Program
from models.section import Section
from models.time_slot import TimeSlot
from models.section_time_window import SectionTimeWindow

USERNAME='graphicerahill'

db=SessionLocal()
try:
    u=db.execute(select(User).where(User.username==USERNAME)).scalar_one()
    tenant_id=u.tenant_id

    run=db.execute(
        select(TimetableRun)
        .where(TimetableRun.tenant_id==tenant_id)
        .order_by(TimetableRun.created_at.desc())
    ).scalars().first()
    params = dict(getattr(run, 'parameters', {}) or {})
    program_code = str(params.get('program_code') or '').strip()

    program = db.execute(
        select(Program).where(Program.tenant_id==tenant_id, Program.code==program_code)
    ).scalars().one()

    sections = db.execute(
        select(Section.id, Section.code)
        .where(Section.tenant_id==tenant_id, Section.program_id==program.id, Section.is_active.is_(True), Section.code.in_(['BCA-A','BCA-B']))
        .order_by(Section.code.asc())
    ).all()
    if not sections:
        print('NO_TARGET_SECTIONS')
        raise SystemExit(0)

    slot_rows = db.execute(
        select(TimeSlot.day_of_week, TimeSlot.slot_index)
        .where(TimeSlot.tenant_id==tenant_id)
    ).all()
    by_day = {}
    for d, idx in slot_rows:
        by_day.setdefault(int(d), []).append(int(idx))
    day_ranges = {d: (min(v), max(v)) for d, v in by_day.items() if v}

    created = 0
    updated = 0

    for sid, scode in sections:
        existing = db.execute(
            select(SectionTimeWindow)
            .where(SectionTimeWindow.tenant_id==tenant_id, SectionTimeWindow.section_id==sid)
        ).scalars().all()
        by_day_existing = {int(r.day_of_week): r for r in existing}

        for day, (start_idx, end_idx) in sorted(day_ranges.items()):
            row = by_day_existing.get(day)
            if row is None:
                db.add(
                    SectionTimeWindow(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        section_id=sid,
                        day_of_week=day,
                        start_slot_index=start_idx,
                        end_slot_index=end_idx,
                    )
                )
                created += 1
            else:
                changed = False
                if int(row.start_slot_index) != int(start_idx):
                    row.start_slot_index = int(start_idx)
                    changed = True
                if int(row.end_slot_index) != int(end_idx):
                    row.end_slot_index = int(end_idx)
                    changed = True
                if changed:
                    updated += 1

    db.commit()
    print('sections', [s[1] for s in sections])
    print('day_ranges', day_ranges)
    print('created', created)
    print('updated', updated)

except Exception:
    db.rollback()
    raise
finally:
    db.close()
