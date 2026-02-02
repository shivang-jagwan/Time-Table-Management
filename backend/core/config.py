from __future__ import annotations

from pathlib import Path

from pydantic import Field
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

    # Runtime
    environment: str = Field(default="development", validation_alias=AliasChoices("environment", "ENVIRONMENT"))
    frontend_origin: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("frontend_origin", "FRONTEND_ORIGIN"),
    )


settings = Settings()
