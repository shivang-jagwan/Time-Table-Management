"""Dev router removed for production hardening.

This module is intentionally left without any routes.
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()
