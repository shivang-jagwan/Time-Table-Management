from __future__ import annotations

import argparse
import os
from pathlib import Path

import bcrypt
import psycopg2


DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "Default College"
DEFAULT_USERNAME = "graphicerahill"
DEFAULT_PASSWORD = "Graphic@ERA123"


def _hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _normalize_psycopg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return url


def _ensure_tables(cur) -> None:
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            created_at TIMESTAMP DEFAULT now()
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NULL,
            username VARCHAR(100) NOT NULL,
            password_hash TEXT NOT NULL,
            role VARCHAR(20) DEFAULT 'ADMIN',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT now()
        );
        """
    )

    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id UUID;")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'ADMIN';")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")

    # Remove old global uniqueness if present.
    cur.execute("DROP INDEX IF EXISTS ux_users_username;")

    # Tenant-aware uniqueness.
    cur.execute("CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users (tenant_id);")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username_shared ON users (lower(username)) WHERE tenant_id IS NULL;"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_username_tenant ON users (tenant_id, lower(username)) WHERE tenant_id IS NOT NULL;"
    )

    # Best-effort FK.
    cur.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conname = 'fk_users_tenant_id'
          ) THEN
            ALTER TABLE users
            ADD CONSTRAINT fk_users_tenant_id
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
            ON DELETE CASCADE;
          END IF;
        END $$;
        """
    )


def _ensure_default_tenant(cur) -> str:
    cur.execute("select id from tenants where slug = %s limit 1", (DEFAULT_TENANT_SLUG,))
    row = cur.fetchone()
    if row is not None:
        return str(row[0])

    cur.execute(
        "insert into tenants (slug, name) values (%s, %s) returning id",
        (DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME),
    )
    return str(cur.fetchone()[0])


def _ensure_user(cur, *, tenant_id: str, username: str, password: str, role: str) -> bool:
    cur.execute(
        """
        select 1
        from users
        where tenant_id = %s
          and lower(username) = lower(%s)
        limit 1
        """,
        (tenant_id, username),
    )
    if cur.fetchone() is not None:
        return False

    pw_hash = _hash_password(password)

    cur.execute(
        """
        select 1
        from information_schema.columns
        where table_schema='public'
          and table_name='users'
          and column_name='name'
        limit 1
        """.strip()
    )
    has_name = cur.fetchone() is not None

    if has_name:
        cur.execute(
            """
            insert into users (tenant_id, name, username, password_hash, role, is_active)
            values (%s, %s, %s, %s, %s, true)
            """.strip(),
            (tenant_id, username, username, pw_hash, role),
        )
    else:
        cur.execute(
            """
            insert into users (tenant_id, username, password_hash, role, is_active)
            values (%s, %s, %s, %s, true)
            """.strip(),
            (tenant_id, username, pw_hash, role),
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Default College tenant and default admin user (idempotent).")
    parser.add_argument("--username", type=str, default=DEFAULT_USERNAME)
    parser.add_argument("--password", type=str, default=DEFAULT_PASSWORD)
    parser.add_argument("--role", type=str, default="ADMIN")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    _load_env_file(backend_dir / ".env")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not set (backend/.env)")

    conninfo = _normalize_psycopg_url(database_url)

    with psycopg2.connect(conninfo) as conn:
        with conn.cursor() as cur:
            _ensure_tables(cur)
            tenant_id = _ensure_default_tenant(cur)
            created = _ensure_user(
                cur,
                tenant_id=tenant_id,
                username=args.username,
                password=args.password,
                role=(args.role or "ADMIN").strip().upper(),
            )

            if created:
                print(f"OK: created user {args.username!r} in tenant {DEFAULT_TENANT_SLUG!r}")
            else:
                print(f"OK: user {args.username!r} already exists in tenant {DEFAULT_TENANT_SLUG!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
