from __future__ import annotations

import time
from typing import Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import inspect

from core.config import settings
from core.tenancy import get_current_tenant_id


class DatabaseUnavailableError(RuntimeError):
    """Raised when the database is temporarily unreachable (transient connectivity failure)."""


_RETRY_DELAYS_SECONDS: list[float] = [0.2, 0.5, 1.0]


def _iter_exception_messages(exc: BaseException) -> Iterable[str]:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msg = str(cur)
        if msg:
            yield msg
        cur = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)


def is_transient_db_connectivity_error(exc: BaseException) -> bool:
    """Heuristically detect transient DB connectivity failures (DNS/timeouts/refused).

    We intentionally do NOT treat constraint/validation/SQL errors as transient.
    """

    joined = "\n".join(m.lower() for m in _iter_exception_messages(exc))

    # DNS resolution failures
    if "getaddrinfo failed" in joined:
        return True
    if "could not translate host name" in joined:
        return True
    if "name or service not known" in joined:
        return True

    # Connection refused / reset / closed
    if "connection refused" in joined:
        return True
    if "actively refused" in joined:
        return True
    if "connection reset" in joined:
        return True
    if "server closed the connection unexpectedly" in joined:
        return True

    # Timeouts
    if "timeout" in joined:
        return True
    if "timed out" in joined:
        return True

    return False


def get_engine() -> Engine:
    url = settings.database_url.strip()

    # Normalize common Postgres URLs to SQLAlchemy's psycopg2 dialect.
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql+psycopg://"):
        # If an older config used psycopg v3, convert to psycopg2.
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql+psycopg://")

    connect_args: dict[str, object] = {"connect_timeout": 3}

    # Supabase requires SSL. If the URL doesn't specify sslmode, force it for *.supabase.com.
    try:
        parsed = make_url(url)
        host = (parsed.host or "").lower()
        if host.endswith("supabase.com") and "sslmode" not in (parsed.query or {}):
            connect_args["sslmode"] = "require"
    except Exception:
        # If URL parsing fails, fall back to the raw URL; connect_args still applies.
        pass

    # pool_pre_ping helps with stale pooled connections.
    # connect_timeout keeps outages from hanging requests (used by retries and /health).
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


ENGINE = get_engine()
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)


@event.listens_for(Session, "before_flush")
def _inject_tenant_id(session: Session, flush_context, instances) -> None:
    # Enforce tenant_id assignment at the ORM layer so request bodies cannot spoof tenant_id.
    # DB-level constraints still apply (see migrations).
    mode = (settings.tenant_mode or "shared").strip().lower()
    ctx_tenant_id = get_current_tenant_id()

    for obj in session.new:
        if not hasattr(obj, "tenant_id"):
            continue

        obj_tenant_id = getattr(obj, "tenant_id", None)
        if obj_tenant_id is None:
            # In strict modes, tenant_id must be resolved from auth context.
            if mode != "shared" and ctx_tenant_id is None:
                raise ValueError("tenant_id missing for new row (no tenant context)")
            setattr(obj, "tenant_id", ctx_tenant_id)
            continue

        # If caller attempted to set tenant_id explicitly, ensure it matches the request tenant.
        if mode != "shared" and ctx_tenant_id is not None and str(obj_tenant_id) != str(ctx_tenant_id):
            raise ValueError("tenant_id spoofing attempt detected")

    for obj in session.dirty:
        if not hasattr(obj, "tenant_id"):
            continue

        state = inspect(obj)
        if "tenant_id" not in state.attrs:
            continue

        hist = state.attrs.tenant_id.history
        if not hist.has_changes():
            continue

        new_tenant_id = getattr(obj, "tenant_id", None)
        if mode != "shared" and ctx_tenant_id is not None and str(new_tenant_id) != str(ctx_tenant_id):
            raise ValueError("tenant_id change/spoofing attempt detected")


def get_db():
    last_exc: BaseException | None = None

    # Retry session acquisition by doing an explicit lightweight ping (SELECT 1).
    for attempt in range(len(_RETRY_DELAYS_SECONDS) + 1):
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        except OperationalError as exc:
            last_exc = exc
            db.close()
            if not is_transient_db_connectivity_error(exc) or attempt >= len(_RETRY_DELAYS_SECONDS):
                break
            time.sleep(_RETRY_DELAYS_SECONDS[attempt])
            continue
        except Exception as exc:
            # Unexpected errors during connection validation should not be treated as request-scoped failures.
            last_exc = exc
            db.close()
            if not is_transient_db_connectivity_error(exc) or attempt >= len(_RETRY_DELAYS_SECONDS):
                break
            time.sleep(_RETRY_DELAYS_SECONDS[attempt])
            continue

        # Important: do NOT wrap `yield db` in the same try/except as the ping.
        # Exceptions raised by the endpoint should propagate normally (e.g., 409/422),
        # rather than being converted into DatabaseUnavailableError (503).
        try:
            yield db
        finally:
            db.close()
        return

    raise DatabaseUnavailableError("Database temporarily unavailable") from last_exc


def validate_db_connection(db: Session) -> None:
    """Explicitly validate DB connectivity with a lightweight query."""

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        if is_transient_db_connectivity_error(exc):
            raise DatabaseUnavailableError("Database temporarily unavailable") from exc
        raise
