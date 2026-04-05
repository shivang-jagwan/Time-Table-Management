from sqlalchemy import select
from core.database import SessionLocal
from models.user import User
from models.timetable_run import TimetableRun
from models.program import Program
from models.academic_year import AcademicYear
from models.section import Section
from models.section_time_window import SectionTimeWindow
from models.time_slot import TimeSlot

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
    if run is None:
        print('NO_RUN')
        raise SystemExit(0)

    params = dict(getattr(run, 'parameters', {}) or {})
    program_code = str(params.get('program_code') or '').strip()

    print('run_id', run.id)
    print('status', run.status)
    print('program_code', program_code)
    print('academic_year_id', run.academic_year_id)
    print('created_at', run.created_at)

    program = db.execute(
        select(Program).where(Program.tenant_id==tenant_id, Program.code==program_code)
    ).scalars().first()
    if program is None:
        print('PROGRAM_NOT_FOUND_BY_CODE')
        raise SystemExit(0)

    year_num = None
    if run.academic_year_id is not None:
        ay = db.execute(select(AcademicYear).where(AcademicYear.id==run.academic_year_id)).scalars().first()
        year_num = getattr(ay, 'year_number', None)
    print('academic_year_number', year_num)

    slot_days = sorted({int(d) for (d,) in db.execute(select(TimeSlot.day_of_week).where(TimeSlot.tenant_id==tenant_id)).all()})
    print('active_slot_days', slot_days)

    q_sections = select(Section.id, Section.code, Section.academic_year_id).where(
        Section.tenant_id==tenant_id,
        Section.program_id==program.id,
        Section.is_active.is_(True),
    )
    if run.academic_year_id is not None:
        q_sections = q_sections.where(Section.academic_year_id==run.academic_year_id)

    sections = db.execute(q_sections.order_by(Section.code.asc())).all()
    print('active_sections_in_scope', len(sections))

    sec_ids = [sid for sid, _code, _ay in sections]
    rows = db.execute(
        select(SectionTimeWindow.section_id, SectionTimeWindow.day_of_week)
        .where(SectionTimeWindow.tenant_id==tenant_id)
        .where(SectionTimeWindow.section_id.in_(sec_ids))
    ).all()

    days_by_sec = {}
    for sid, d in rows:
        days_by_sec.setdefault(sid, set()).add(int(d))

    missing = []
    for sid, code, ayid in sections:
        present = days_by_sec.get(sid, set())
        miss = [d for d in slot_days if d not in present]
        if miss:
            missing.append((code, sid, miss))

    print('sections_with_missing_windows', len(missing))
    for code, sid, miss in missing:
        print(code, sid, 'missing_days', miss)
finally:
    db.close()
