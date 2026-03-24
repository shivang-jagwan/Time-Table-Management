from __future__ import annotations

import json
import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency in some environments
    redis = None


_client = None
_init_attempted = False


def _get_client():
    global _client, _init_attempted
    if _client is not None:
        return _client
    if _init_attempted:
        return None
    _init_attempted = True

    if not settings.redis_enabled:
        return None
    if not settings.redis_url:
        logger.warning("Redis cache enabled but REDIS_URL is not set; caching disabled")
        return None
    if redis is None:
        logger.warning("Redis package not available; caching disabled")
        return None

    try:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
        _client.ping()
        logger.info("Redis cache connected")
    except Exception:
        logger.exception("Failed to connect to Redis; caching disabled")
        _client = None
    return _client


def cache_get_json(key: str) -> Any | None:
    client = _get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.exception("Redis cache get failed key=%s", key)
        return None


def cache_set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    client = _get_client()
    if client is None:
        return
    ttl = int(ttl_seconds or settings.cache_ttl_seconds)
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        logger.exception("Redis cache set failed key=%s", key)


def cache_delete_prefix(prefix: str) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        keys = list(client.scan_iter(match=f"{prefix}*", count=200))
        if keys:
            client.delete(*keys)
    except Exception:
        logger.exception("Redis cache delete prefix failed prefix=%s", prefix)
