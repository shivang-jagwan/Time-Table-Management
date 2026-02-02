import os
import sys

from sqlalchemy import create_engine, text


def load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[7:].lstrip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
                    value = value[1:-1]
                env[key] = value
    except FileNotFoundError:
        return {}
    return env


def main() -> int:
    env_from_file = load_env_file(".env")
    db_url = env_from_file.get("DATABASE_URL") or os.getenv("DATABASE_URL")

    if not db_url:
        print("SUPABASE_DB_CHECK: MISSING_DATABASE_URL")
        return 2

    try:
        engine = create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        print("SUPABASE_DB_OK")
        return 0
    except Exception as exc:
        print("SUPABASE_DB_FAIL")
        print(f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
