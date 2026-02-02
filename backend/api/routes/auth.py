from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_current_user
from core.config import settings
from core.db import get_db
from core.security import create_access_token, hash_password, verify_password
from models.user import User
from schemas.auth import LoginRequest, LoginResponse, MeResponse, SignupRequest, SignupResponse


router = APIRouter()

logger = logging.getLogger(__name__)


# Simple in-memory rate limiting for login.
# NOTE: In multi-worker deployments this is per-worker. For enterprise-grade limiting,
# put this behind a reverse proxy or use Redis-backed rate limiting.
_LOGIN_WINDOW_SECONDS = 60
_LOGIN_MAX_ATTEMPTS_PER_KEY = 12
_login_attempts: dict[str, list[float]] = {}


def _rate_limit_key(request: Request, username: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{username.lower().strip()}"


def _enforce_login_rate_limit(request: Request, username: str) -> None:
    key = _rate_limit_key(request, username)
    now = time.time()
    history = _login_attempts.get(key, [])
    history = [t for t in history if now - t < _LOGIN_WINDOW_SECONDS]
    history.append(now)
    _login_attempts[key] = history
    if len(history) > _LOGIN_MAX_ATTEMPTS_PER_KEY:
        raise HTTPException(status_code=429, detail="RATE_LIMITED")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    username = str(payload.username or "").strip()
    _enforce_login_rate_limit(request, username)

    ip = request.client.host if request.client else "unknown"

    # Be forgiving about casing/whitespace on input.
    user = (
        db.execute(select(User).where(func.lower(User.username) == func.lower(username)))
        .scalar_one_or_none()
    )
    if user is None:
        logger.warning(
            "Login failed (unknown user) ip=%s username=%r username_len=%d",
            ip,
            username,
            len(username),
        )
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")
    if not user.is_active:
        logger.warning(
            "Login failed (disabled user) ip=%s username=%r username_len=%d",
            ip,
            username,
            len(username),
        )
        raise HTTPException(status_code=403, detail="USER_DISABLED")

    password = str(payload.password or "")
    password_stripped = password.strip()
    password_has_outer_whitespace = password != password_stripped

    password_ok = verify_password(password, user.password_hash)
    if not password_ok and password_has_outer_whitespace:
        # Common UX issue: copy/paste adds a trailing newline/space.
        password_ok = verify_password(password_stripped, user.password_hash)
        if password_ok:
            logger.warning(
                "Login password had surrounding whitespace; accepted after trimming ip=%s username=%r",
                ip,
                username,
            )

    if not password_ok:
        logger.warning(
            "Login failed (bad password) ip=%s username=%r username_len=%d password_len=%d outer_ws=%s",
            ip,
            username,
            len(username),
            len(password),
            password_has_outer_whitespace,
        )
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")

    token = create_access_token(user_id=str(user.id), username=user.username, role=user.role)

    secure_cookie = settings.environment.lower() == "production"
    samesite = (settings.cookie_samesite or "lax").lower().strip()
    if samesite not in {"lax", "strict", "none"}:
        raise HTTPException(status_code=500, detail="INVALID_COOKIE_SAMESITE")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    return LoginResponse(ok=True)


@router.post("/signup", response_model=SignupResponse)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SignupResponse:
    is_production = settings.environment.lower() == "production"
    if is_production and not settings.allow_signup:
        raise HTTPException(status_code=403, detail="SIGNUP_DISABLED")

    username = str(payload.username or "").strip()
    _enforce_login_rate_limit(request, username)

    if not username:
        raise HTTPException(status_code=422, detail="INVALID_USERNAME")

    ip = request.client.host if request.client else "unknown"

    # Enforce case-insensitive uniqueness to avoid multiple rows that would break login.
    existing = (
        db.execute(select(User.id).where(func.lower(User.username) == func.lower(username)))
        .scalar_one_or_none()
    )
    if existing is not None:
        logger.warning("Signup rejected (username taken) ip=%s username=%r", ip, username)
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")

    password_hash = hash_password(str(payload.password or ""))
    role = (settings.signup_default_role or "USER").upper().strip()
    if role not in {"ADMIN", "USER"}:
        raise HTTPException(status_code=500, detail="INVALID_SIGNUP_DEFAULT_ROLE")

    # Some legacy DBs have a NOT NULL `name` column; insert into it when present.
    has_name = (
        db.execute(
            text(
                """
                select 1
                from information_schema.columns
                where table_schema='public'
                  and table_name='users'
                  and column_name='name'
                limit 1
                """.strip()
            )
        ).first()
        is not None
    )

    try:
        if has_name:
            row = db.execute(
                text(
                    """
                    insert into users (name, username, password_hash, role, is_active)
                    values (:name, :username, :password_hash, :role, true)
                    returning id, username, role
                    """.strip()
                ),
                {
                    "name": username,
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                },
            ).first()
        else:
            row = db.execute(
                text(
                    """
                    insert into users (username, password_hash, role, is_active)
                    values (:username, :password_hash, :role, true)
                    returning id, username, role
                    """.strip()
                ),
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                },
            ).first()

        if row is None:
            raise HTTPException(status_code=500, detail="SIGNUP_FAILED")

        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Signup rejected (integrity error) ip=%s username=%r", ip, username)
        raise HTTPException(status_code=409, detail="USERNAME_TAKEN")

    user_id = str(row[0])
    created_username = str(row[1])
    created_role = str(row[2])

    # Auto-login after signup (sets the same cookie as /login).
    token = create_access_token(user_id=user_id, username=created_username, role=created_role)
    secure_cookie = settings.environment.lower() == "production"
    samesite = (settings.cookie_samesite or "lax").lower().strip()
    if samesite not in {"lax", "strict", "none"}:
        raise HTTPException(status_code=500, detail="INVALID_COOKIE_SAMESITE")
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )

    logger.info("Signup success ip=%s username=%r", ip, created_username)
    return SignupResponse(ok=True)


@router.post("/logout")
def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
