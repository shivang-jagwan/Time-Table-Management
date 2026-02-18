from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.tenant import get_by_id, where_tenant
from models.program import Program
from models.section import Section
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
    tenant_id=None,
) -> tuple[Program | None, list[SectionCurriculum]]:
    program = (
        db.execute(where_tenant(select(Program).where(Program.code == program_code), Program, tenant_id))
        .scalar_one_or_none()
    )
    if program is None:
        return None, []

    sections = (
        db.execute(
            where_tenant(
                select(Section)
                .where(Section.program_id == program.id)
                .where(Section.academic_year_id == academic_year_id)
                .where(Section.is_active.is_(True))
                .order_by(Section.code),
                Section,
                tenant_id,
            )
        )
        .scalars()
        .all()
    )

    curricula: list[SectionCurriculum] = []
    for section in sections:
        rows = (
            db.execute(
                where_tenant(
                    select(TrackSubject)
                    .where(TrackSubject.program_id == program.id)
                    .where(TrackSubject.academic_year_id == academic_year_id)
                    .where(TrackSubject.track == section.track),
                    TrackSubject,
                    tenant_id,
                )
            )
            .scalars()
            .all()
        )

        mandatory_ids = [r.subject_id for r in rows if not r.is_elective]
        elective_ids = [r.subject_id for r in rows if r.is_elective]

        mandatory_subjects = (
            db.execute(where_tenant(select(Subject).where(Subject.id.in_(mandatory_ids)), Subject, tenant_id))
            .scalars()
            .all()
            if mandatory_ids
            else []
        )
        elective_options = (
            db.execute(where_tenant(select(Subject).where(Subject.id.in_(elective_ids)), Subject, tenant_id))
            .scalars()
            .all()
            if elective_ids
            else []
        )

        chosen_elective = None
        # Legacy section_electives table has been removed in favor of elective blocks.
        # This service is currently kept for backwards compatibility, but does not
        # attempt to infer a single chosen elective.

        curricula.append(
            SectionCurriculum(
                section=section,
                mandatory_subjects=mandatory_subjects,
                elective_options=elective_options,
                chosen_elective=chosen_elective,
            )
        )

    return program, curricula
