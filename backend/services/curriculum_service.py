from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.program import Program
from models.section import Section
from models.section_elective import SectionElective
from models.subject import Subject
from models.track_subject import TrackSubject


@dataclass(frozen=True)
class SectionCurriculum:
    section: Section
    mandatory_subjects: list[Subject]
    elective_options: list[Subject]
    chosen_elective: Subject | None


def load_curricula(
    db: Session,
    *,
    program_code: str,
    academic_year_id,
) -> tuple[Program | None, list[SectionCurriculum]]:
    program = db.execute(select(Program).where(Program.code == program_code)).scalar_one_or_none()
    if program is None:
        return None, []

    sections = (
        db.execute(
            select(Section)
            .where(Section.program_id == program.id)
            .where(Section.academic_year_id == academic_year_id)
            .where(Section.is_active.is_(True))
            .order_by(Section.code)
        )
        .scalars()
        .all()
    )

    curricula: list[SectionCurriculum] = []
    for section in sections:
        rows = (
            db.execute(
                select(TrackSubject)
                .where(TrackSubject.program_id == program.id)
                .where(TrackSubject.academic_year_id == academic_year_id)
                .where(TrackSubject.track == section.track)
            )
            .scalars()
            .all()
        )

        mandatory_ids = [r.subject_id for r in rows if not r.is_elective]
        elective_ids = [r.subject_id for r in rows if r.is_elective]

        mandatory_subjects = (
            db.execute(select(Subject).where(Subject.id.in_(mandatory_ids)))
            .scalars()
            .all()
            if mandatory_ids
            else []
        )
        elective_options = (
            db.execute(select(Subject).where(Subject.id.in_(elective_ids))).scalars().all()
            if elective_ids
            else []
        )

        chosen_elective = None
        if elective_ids:
            selection = (
                db.execute(select(SectionElective).where(SectionElective.section_id == section.id))
                .scalars()
                .first()
            )
            if selection is not None:
                chosen_elective = db.get(Subject, selection.subject_id)

        curricula.append(
            SectionCurriculum(
                section=section,
                mandatory_subjects=mandatory_subjects,
                elective_options=elective_options,
                chosen_elective=chosen_elective,
            )
        )

    return program, curricula
