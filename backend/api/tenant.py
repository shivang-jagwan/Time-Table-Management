from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session


def where_tenant(stmt, model, tenant_id: uuid.UUID | None):
    # NOTE: In shared mode, we intentionally scope to tenant_id IS NULL.
    # This prevents shared deployments from accidentally seeing per-tenant data.
    if tenant_id is None:
        return stmt.where(model.tenant_id.is_(None))
    return stmt.where(model.tenant_id == tenant_id)


def get_by_id(db: Session, model, obj_id: uuid.UUID, tenant_id: uuid.UUID | None):
    q = select(model).where(model.id == obj_id)
    q = where_tenant(q, model, tenant_id)
    return db.execute(q).scalars().first()
