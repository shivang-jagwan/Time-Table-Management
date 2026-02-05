from __future__ import annotations

import uuid
from contextvars import ContextVar


current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("current_tenant_id", default=None)


def set_current_tenant_id(tenant_id: uuid.UUID | None) -> None:
    current_tenant_id.set(tenant_id)


def get_current_tenant_id() -> uuid.UUID | None:
    return current_tenant_id.get()
