"""Legacy admin routes module.

This project is academic-year-only. The legacy admin API has been replaced by
`api.routes.admin_v2`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


router = APIRouter()


@router.get("/{path:path}")
def _admin_legacy_get(path: str):
    raise HTTPException(status_code=410, detail="ADMIN_ENDPOINT_MOVED_USE_ADMIN_V2")


@router.post("/{path:path}")
def _admin_legacy_post(path: str):
    raise HTTPException(status_code=410, detail="ADMIN_ENDPOINT_MOVED_USE_ADMIN_V2")


@router.put("/{path:path}")
def _admin_legacy_put(path: str):
    raise HTTPException(status_code=410, detail="ADMIN_ENDPOINT_MOVED_USE_ADMIN_V2")


@router.patch("/{path:path}")
def _admin_legacy_patch(path: str):
    raise HTTPException(status_code=410, detail="ADMIN_ENDPOINT_MOVED_USE_ADMIN_V2")


@router.delete("/{path:path}")
def _admin_legacy_delete(path: str):
    raise HTTPException(status_code=410, detail="ADMIN_ENDPOINT_MOVED_USE_ADMIN_V2")


__all__ = ["router"]
