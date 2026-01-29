from __future__ import annotations

from fastapi import APIRouter

from core.security import create_access_token
from schemas.auth import DevLoginResponse


router = APIRouter()


@router.post("/dev-login", response_model=DevLoginResponse)
def dev_login() -> DevLoginResponse:
    token = create_access_token(subject="admin")
    return DevLoginResponse(access_token=token)
