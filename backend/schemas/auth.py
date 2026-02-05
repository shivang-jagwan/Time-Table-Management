from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant: str | None = Field(default=None, max_length=80)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class SignupRequest(BaseModel):
    tenant: str | None = Field(default=None, max_length=80)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=256)


class SignupResponse(BaseModel):
    ok: bool = True


class LoginResponse(BaseModel):
    ok: bool = True
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    username: str
    role: str
    is_active: bool
    created_at: datetime
