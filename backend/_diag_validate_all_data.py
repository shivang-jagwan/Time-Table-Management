#!/usr/bin/env python3
"""Run prerequisite validation across all tenant data.

Checks every active program in the tenant in two scopes:
- Year scope: each active academic year that has active sections in that program.
- Global scope: all active sections in that program (academic_year_id=None).

This script is read-only and does not modify data.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import and_, select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import SessionLocal  # noqa: E402
from models import AcademicYear, Program, Section, User  # noqa: E402
from services.solver_validation import validate_prereqs  # noqa: E402


@dataclass
class ScopeResult:
    label: str
    sections_count: int
    errors: int
    warnings: int


class _TransientRun:
    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="shivang123", help="Username used to resolve tenant")
    parser.add_argument(
        "--show-top",
        type=int,
        default=25,
        help="How many top conflict types to print (default: 25)",
    )
    return parser.parse_args()


def _severity_of(conflict) -> str:
    return str(getattr(conflict, "severity", "ERROR") or "ERROR").upper()


def main() -> int:
    args = _parse_args()
    db = SessionLocal()

    try:
        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if user is None:
            print(f"[ERROR] user not found: {args.username}")
            return 1

        tenant_id = user.tenant_id
        if tenant_id is None:
            print("[ERROR] user has no tenant_id")
            return 1

        programs = (
            db.execute(
                select(Program)
                .where(Program.tenant_id == tenant_id)
                .order_by(Program.code.asc())
            )
            .scalars()
            .all()
        )
        if not programs:
            print("[OK] no programs found for tenant")
            return 0

        years = (
            db.execute(
                select(AcademicYear)
                .where(and_(AcademicYear.tenant_id == tenant_id, AcademicYear.is_active.is_(True)))
                .order_by(AcademicYear.year_number.asc())
            )
            .scalars()
            .all()
        )
        year_by_id = {y.id: y for y in years}

        print("=" * 80)
        print("TENANT-WIDE PREREQUISITE VALIDATION")
        print("=" * 80)
        print(f"tenant_id: {tenant_id}")
        print(f"programs: {len(programs)}")
        print(f"active academic years: {len(years)}")

        total_scopes = 0
        failed_scopes = 0
        total_errors = 0
        total_warnings = 0
        by_type = Counter()
        by_type_error = Counter()
        by_type_warn = Counter()

        for program in programs:
            print("\n" + "-" * 80)
            print(f"Program: {program.code} ({program.id})")

            prog_sections_all = (
                db.execute(
                    select(Section)
                    .where(
                        and_(
                            Section.tenant_id == tenant_id,
                            Section.program_id == program.id,
                            Section.is_active.is_(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if not prog_sections_all:
                print("  [SKIP] no active sections")
                continue

            scope_results: list[ScopeResult] = []

            # Year scopes.
            year_ids_present = sorted({s.academic_year_id for s in prog_sections_all if s.academic_year_id is not None}, key=str)
            for year_id in year_ids_present:
                year_sections = [s for s in prog_sections_all if s.academic_year_id == year_id]
                if not year_sections:
                    continue

                transient_run = _TransientRun(tenant_id)
                conflicts = validate_prereqs(
                    db,
                    run=transient_run,
                    program_id=program.id,
                    academic_year_id=year_id,
                    sections=year_sections,
                )

                errors = 0
                warnings = 0
                for c in conflicts:
                    ctype = str(getattr(c, "conflict_type", "UNKNOWN"))
                    sev = _severity_of(c)
                    by_type[ctype] += 1
                    if sev == "WARN":
                        warnings += 1
                        by_type_warn[ctype] += 1
                    else:
                        errors += 1
                        by_type_error[ctype] += 1

                year_no = getattr(year_by_id.get(year_id), "year_number", "?")
                label = f"Year-{year_no}"
                scope_results.append(
                    ScopeResult(label=label, sections_count=len(year_sections), errors=errors, warnings=warnings)
                )
                total_scopes += 1
                total_errors += errors
                total_warnings += warnings
                if errors > 0:
                    failed_scopes += 1

            # Program-global scope.
            transient_run = _TransientRun(tenant_id)
            conflicts = validate_prereqs(
                db,
                run=transient_run,
                program_id=program.id,
                academic_year_id=None,
                sections=prog_sections_all,
            )
            errors = 0
            warnings = 0
            for c in conflicts:
                ctype = str(getattr(c, "conflict_type", "UNKNOWN"))
                sev = _severity_of(c)
                by_type[ctype] += 1
                if sev == "WARN":
                    warnings += 1
                    by_type_warn[ctype] += 1
                else:
                    errors += 1
                    by_type_error[ctype] += 1

            scope_results.append(
                ScopeResult(label="Global", sections_count=len(prog_sections_all), errors=errors, warnings=warnings)
            )
            total_scopes += 1
            total_errors += errors
            total_warnings += warnings
            if errors > 0:
                failed_scopes += 1

            for r in scope_results:
                status = "OK" if r.errors == 0 else "FAILED"
                print(
                    f"  {r.label:>8} | sections={r.sections_count:>3} | errors={r.errors:>3} | warnings={r.warnings:>3} | {status}"
                )

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"scopes checked: {total_scopes}")
        print(f"scopes failed: {failed_scopes}")
        print(f"total errors: {total_errors}")
        print(f"total warnings: {total_warnings}")

        print("\nTop conflict types (all severities):")
        for conflict_type, count in by_type.most_common(max(1, args.show_top)):
            e = by_type_error.get(conflict_type, 0)
            w = by_type_warn.get(conflict_type, 0)
            print(f"  {conflict_type}: {count} (ERROR={e}, WARN={w})")

        # Non-zero exit if any scope has errors.
        return 2 if failed_scopes > 0 else 0

    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
