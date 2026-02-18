from __future__ import annotations

# Backwards-compatible re-exports.
# The actual SQLAlchemy engine/session setup lives in core/database.py.
from core.database import (  # noqa: F401
    DatabaseUnavailableError,
    ENGINE,
    SessionLocal,
    get_db,
    is_transient_db_connectivity_error,
    table_exists,
    validate_db_connection,
)

__all__ = [
    "DatabaseUnavailableError",
    "ENGINE",
    "SessionLocal",
    "get_db",
    "is_transient_db_connectivity_error",
    "table_exists",
    "validate_db_connection",
]
