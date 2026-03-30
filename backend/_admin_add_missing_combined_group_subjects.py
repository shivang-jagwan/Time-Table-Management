#!/usr/bin/env python3
"""Backfill missing SectionSubject rows required by combined groups.

For each combined-group section membership, ensures the combined group's subject
is present in section_subjects for that section (tenant-scoped).

Usage:
  python _admin_add_missing_combined_group_subjects.py --username shivang123
  python _admin_add_missing_combined_group_subjects.py --username shivang123 --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid

from sqlalchemy import and_, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal  # noqa: E402
from models import (  # noqa: E402
    CombinedGroup,
    CombinedGroupSection,
    Section,
    SectionSubject,
    Subject,
    User,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shivang123", help="Username used to resolve tenant scope")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    db = SessionLocal()

    try:
        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if not user:
            print(f"[ERROR] user not found: {args.username}")
            return 1

        tenant_id = user.tenant_id
        if tenant_id is None:
            print("[ERROR] user has no tenant_id")
            return 1

        rows = (
            db.execute(
                select(
                    CombinedGroup.id,
                    CombinedGroup.subject_id,
                    CombinedGroupSection.section_id,
                )
                .join(
                    CombinedGroupSection,
                    and_(
                        CombinedGroupSection.combined_group_id == CombinedGroup.id,
                        CombinedGroupSection.tenant_id == CombinedGroup.tenant_id,
                    ),
                )
                .where(CombinedGroup.tenant_id == tenant_id)
                .where(CombinedGroupSection.tenant_id == tenant_id)
            )
            .all()
        )

        if not rows:
            print("[OK] no combined group rows found")
            return 0

        # Keep only memberships for sections that still exist in this tenant.
        section_ids = list({section_id for _gid, _subj_id, section_id in rows})
        existing_section_ids = set(
            db.execute(
                select(Section.id)
                .where(Section.id.in_(section_ids))
                .where(Section.tenant_id == tenant_id)
            )
            .scalars()
            .all()
        )

        candidate_pairs = {
            (section_id, subject_id)
            for _gid, subject_id, section_id in rows
            if section_id in existing_section_ids and subject_id is not None
        }

        if not candidate_pairs:
            print("[OK] no valid section-subject pairs to check")
            return 0

        existing_pairs = set(
            db.execute(
                select(SectionSubject.section_id, SectionSubject.subject_id)
                .where(SectionSubject.tenant_id == tenant_id)
                .where(SectionSubject.section_id.in_([sec for sec, _subj in candidate_pairs]))
            )
            .all()
        )

        missing_pairs = sorted(candidate_pairs - existing_pairs, key=lambda p: (str(p[0]), str(p[1])))

        subject_code_by_id = {
            sid: code
            for sid, code in db.execute(
                select(Subject.id, Subject.code)
                .where(Subject.id.in_([subj for _sec, subj in missing_pairs]))
                .where(Subject.tenant_id == tenant_id)
            ).all()
        }

        print("=" * 72)
        print("BACKFILL COMBINED-GROUP SUBJECTS INTO SECTION_SUBJECTS")
        print("=" * 72)
        print(f"tenant_id: {tenant_id}")
        print(f"combined memberships checked: {len(rows)}")
        print(f"candidate section-subject pairs: {len(candidate_pairs)}")
        print(f"already present: {len(candidate_pairs) - len(missing_pairs)}")
        print(f"missing: {len(missing_pairs)}")

        if not missing_pairs:
            print("[OK] nothing to insert")
            return 0

        print("\nMissing pairs:")
        for section_id, subject_id in missing_pairs:
            code = subject_code_by_id.get(subject_id, "<unknown>")
            print(f"  section={section_id} subject={subject_id} code={code}")

        if args.dry_run:
            print("\n[DRY RUN] no rows inserted")
            return 0

        for section_id, subject_id in missing_pairs:
            db.add(
                SectionSubject(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    section_id=section_id,
                    subject_id=subject_id,
                )
            )

        db.commit()
        print(f"\n[OK] inserted {len(missing_pairs)} section_subject rows")
        return 0

    except Exception as exc:
        db.rollback()
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
