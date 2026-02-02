from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from core.config import BACKEND_DIR


def setup_logging(*, environment: str) -> None:
    """Configure application logging.

    - Dev: console logs, DEBUG level.
    - Prod: console + rotating file logs, INFO level.

    Safe to call multiple times (won't double-add handlers).
    """

    root = logging.getLogger()
    if root.handlers:
        return

    env = (environment or "development").lower().strip()
    level = logging.INFO if env == "production" else logging.DEBUG

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    handlers: list[logging.Handler] = []

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    handlers.append(console)

    if env == "production":
        logs_dir = Path(BACKEND_DIR) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            logs_dir / "app.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)

    # Keep common noisy loggers reasonable.
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
