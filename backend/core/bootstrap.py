from __future__ import annotations

import logging

from sqlalchemy import text

from core.config import settings
from core.db import ENGINE
from core.security import hash_password


logger = logging.getLogger(__name__)


def _ensure_users_schema(conn) -> None:
    # Keep this idempotent: safe across deploys.
    statements = [
        "CREATE EXTENSION IF NOT EXISTS pgcrypto;",
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) DEFAULT 'ADMIN',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT now()
        );
        """,
        # Legacy compatibility: some DBs already have public.users with older columns.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
        # Backfill username from legacy `name` if present.
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='users' AND column_name='name'
          ) THEN
            EXECUTE 'UPDATE users SET username = COALESCE(username, name::text) WHERE username IS NULL';
          END IF;
        END $$;
        """,
        # Ensure we have a unique index for ON CONFLICT.
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username ON users (username);",
    ]

    for s in statements:
        conn.execute(text(s))


def _seed_admin_if_configured(conn) -> None:
    username = settings.seed_admin_username
    password = settings.seed_admin_password
    if not username or not password:
        return

    existing = conn.execute(
        text("select 1 from users where lower(username) = lower(:u) limit 1"),
        {"u": username},
    ).first()
    if existing is not None:
        return

    password_hash = hash_password(password)

    has_name = (
        conn.execute(
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

    if has_name:
        conn.execute(
            text(
                """
                insert into users (name, username, password_hash, role, is_active)
                values (:name, :username, :password_hash, 'ADMIN', true)
                on conflict (username) do nothing
                """.strip()
            ),
            {
                "name": username,
                "username": username,
                "password_hash": password_hash,
            },
        )
    else:
        conn.execute(
            text(
                """
                insert into users (username, password_hash, role, is_active)
                values (:username, :password_hash, 'ADMIN', true)
                on conflict (username) do nothing
                """.strip()
            ),
            {
                "username": username,
                "password_hash": password_hash,
            },
        )

    logger.warning(
        "Seeded initial admin user from env (username=%r). Change the password after first login.",
        username,
    )


def bootstrap_auth() -> None:
    """Best-effort auth bootstrap for production deployments.

    - Ensures `users` table exists and has required columns.
    - Optionally seeds an admin user if SEED_ADMIN_USERNAME + SEED_ADMIN_PASSWORD are set.

    This function is safe to run on every startup.
    """

    with ENGINE.begin() as conn:
        _ensure_users_schema(conn)
        _seed_admin_if_configured(conn)
