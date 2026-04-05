from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.tenant import where_tenant
from core.database import is_transient_db_connectivity_error
from models.timetable_conflict import TimetableConflict
from models.timetable_entry import TimetableEntry
from models.timetable_run import TimetableRun


_SAVE_RETRY_DELAYS_SECONDS: list[float] = [0.2, 0.5, 1.0]


def save_run_outputs_with_retry(
    db: Session,
    *,
    run: TimetableRun,
    tenant_id: Any | None,
    entries: Sequence[TimetableEntry] | None = None,
    conflicts: Sequence[TimetableConflict] | None = None,
    clear_existing_entries: bool = False,
) -> None:
    """Persist run outputs with retry on transient DB connectivity failures.

    The solver should execute fully in memory. This function is called only
    after solve completion to persist buffered objects in bulk.
    """

    buffered_entries = list(entries or [])
    buffered_conflicts = list(conflicts or [])

    last_exc: BaseException | None = None
    for attempt in range(len(_SAVE_RETRY_DELAYS_SECONDS) + 1):
        try:
            if clear_existing_entries:
                stmt = delete(TimetableEntry).where(TimetableEntry.run_id == run.id)
                stmt = where_tenant(stmt, TimetableEntry, tenant_id)
                db.execute(stmt)

            if buffered_entries:
                db.bulk_save_objects(buffered_entries)
            if buffered_conflicts:
                db.bulk_save_objects(buffered_conflicts)

            db.add(run)
            db.commit()
            return
        except Exception as exc:
            last_exc = exc
            try:
                db.rollback()
            except Exception:
                pass

            if not is_transient_db_connectivity_error(exc):
                raise
            if attempt >= len(_SAVE_RETRY_DELAYS_SECONDS):
                raise

            time.sleep(_SAVE_RETRY_DELAYS_SECONDS[attempt])

    if last_exc is not None:
        raise last_exc
