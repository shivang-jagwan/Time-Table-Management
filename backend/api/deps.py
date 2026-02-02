from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import uuid

from core.security import decode_token
from core.db import get_db
from models.user import User


bearer_scheme = HTTPBearer(auto_error=False)


def _extract_token(request: Request, creds: HTTPAuthorizationCredentials | None) -> str | None:
    if creds is not None and creds.credentials:
        return creds.credentials
    cookie_token = request.cookies.get("access_token")
    return cookie_token or None


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    cached = getattr(request.state, "current_user", None)
    if isinstance(cached, User):
        return cached

    token = _extract_token(request, creds)
    if not token:
        raise HTTPException(status_code=401, detail="NOT_AUTHENTICATED")
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

    try:
        user_uuid = uuid.UUID(str(user_id))
    except Exception:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

    user = db.get(User, user_uuid)
    if user is None:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="USER_DISABLED")

    request.state.current_user = user
    request.state.auth_payload = payload
    return user


def require_admin(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    payload = getattr(request.state, "auth_payload", None)
    if not isinstance(payload, dict):
        payload = {}

    role = (current_user.role or "").upper()
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="NOT_AUTHORIZED")
    return payload
