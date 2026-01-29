from __future__ import annotations

from fastapi import APIRouter

from core.security import create_access_token
from schemas.auth import DevLoginResponse


router = APIRouter()


@router.post("/token", response_model=DevLoginResponse)
def dev_token() -> DevLoginResponse:
    """Dev-only token minting endpoint.

    Purposefully avoids 'auth'/'login' in the URL path to reduce the chance of
    browser extensions blocking it on localhost.
    """

    token = create_access_token(subject="admin")
    return DevLoginResponse(access_token=token)
