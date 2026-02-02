from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic.aliases import AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")

    database_url: str

    # Auth
    jwt_secret_key: str = Field(
        validation_alias=AliasChoices("jwt_secret_key", "jwt_secret", "JWT_SECRET_KEY", "JWT_SECRET")
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias=AliasChoices("jwt_algorithm", "JWT_ALGORITHM"))
    access_token_expire_minutes: int = Field(
        default=480,
        validation_alias=AliasChoices("access_token_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES"),
    )

    cookie_samesite: str = Field(
        default="lax",
        validation_alias=AliasChoices("cookie_samesite", "COOKIE_SAMESITE"),
    )

    allow_signup: bool = Field(
        default=True,
        validation_alias=AliasChoices("allow_signup", "ALLOW_SIGNUP"),
    )

    signup_default_role: str = Field(
        default="USER",
        validation_alias=AliasChoices("signup_default_role", "SIGNUP_DEFAULT_ROLE"),
    )

    # Optional production bootstrap (recommended): seed an initial admin user.
    # Only used if BOTH username + password are provided.
    seed_admin_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "seed_admin_username",
            "SEED_ADMIN_USERNAME",
            "ADMIN_SEED_USERNAME",
        ),
    )
    seed_admin_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "seed_admin_password",
            "SEED_ADMIN_PASSWORD",
            "ADMIN_SEED_PASSWORD",
        ),
    )

    # Runtime
    environment: str = Field(default="development", validation_alias=AliasChoices("environment", "ENVIRONMENT"))
    frontend_origin: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("frontend_origin", "FRONTEND_ORIGIN"),
    )

    @field_validator("frontend_origin")
    @classmethod
    def _normalize_frontend_origin(cls, v: str) -> str:
        # Render/Vercel UI often leads people to paste a trailing slash.
        # Starlette CORS expects the Origin to match exactly (no trailing slash).
        return v.strip().rstrip("/")

    @field_validator("cookie_samesite")
    @classmethod
    def _normalize_cookie_samesite(cls, v: str) -> str:
        return (v or "lax").strip().lower()

    @field_validator("signup_default_role")
    @classmethod
    def _normalize_signup_default_role(cls, v: str) -> str:
        return (v or "USER").strip().upper()

    @field_validator("seed_admin_username")
    @classmethod
    def _normalize_seed_admin_username(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("seed_admin_password")
    @classmethod
    def _normalize_seed_admin_password(cls, v: str | None) -> str | None:
        if v is None:
            return None
        # Intentionally do not strip whitespace here: passwords can contain spaces.
        return v


settings = Settings()
