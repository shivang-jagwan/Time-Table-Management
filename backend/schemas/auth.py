from __future__ import annotations

from pydantic import BaseModel


class DevLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
